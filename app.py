import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import io

# ==========================================
# 設定と準備
# ==========================================
st.set_page_config(
    page_title="画像解析アプリ", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

hide_streamlit_style = """
            <style>
            /* ヘッダー（GitHubアイコンやバー）を隠す */
            header {visibility: hidden;}
            
            /* フッター（Made with Streamlit）を隠す */
            footer {visibility: hidden;}
            
            /* (任意) 右上のハンバーガーメニューも隠したい場合はコメントアウトを外す */
            /* #MainMenu {visibility: hidden;} */
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Gemini設定
genai.configure(api_key=st.secrets["general"]["gemini_api_key"])
model = genai.GenerativeModel('gemini-2.5-flash-lite')

# ==========================================
# 関数定義
# ==========================================

# 1. Google Driveへのアップロード関数 (改良版)
def upload_to_drive(file_obj, filename):
    try:
        creds_dict = dict(st.secrets["connections"]["gsheets"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': filename,
            'parents': [st.secrets["general"]["drive_folder_id"]]
        }
        
        media = io.BytesIO(file_obj.getvalue())
        from googleapiclient.http import MediaIoBaseUpload
        media_body = MediaIoBaseUpload(media, mimetype=file_obj.type)

        # supportsAllDrives=True を追加（共有ドライブ対応のため）
        file = service.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id, webViewLink',
            supportsAllDrives=True 
        ).execute()
        
        return file.get('webViewLink')
        
    except Exception as e:
        # エラーを表示するが、Noneを返して処理を止めない
        print(f"Drive Upload Error: {e}") 
        return None

# 2. ログイン処理関数
def login():
    st.markdown("### 🔐 ログイン")
    
    with st.form("login_form"):
        uid = st.text_input("ユーザーID")
        password = st.text_input("パスワード", type="password")
        submit = st.form_submit_button("ログイン", use_container_width=True)
        
        if submit:
            conn = st.connection("gsheets", type=GSheetsConnection)
            try:
                df = conn.read(worksheet="Users", ttl=0)
                if 'first_login' not in df.columns:
                    df['first_login'] = ""
                
                # ID/Pass照合
                match_indices = df.index[
                    (df['username'].astype(str) == uid) & 
                    (df['password'].astype(str) == password)
                ].tolist()
                
                if match_indices:
                    idx = match_indices[0]
                    current_first_login = str(df.at[idx, 'first_login'])
                    
                    is_valid = False
                    needs_update = False
                    
                    if current_first_login == "" or current_first_login == "nan" or pd.isna(df.at[idx, 'first_login']):
                        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        df.at[idx, 'first_login'] = now_str
                        is_valid = True
                        needs_update = True
                    else:
                        try:
                            first_login_dt = datetime.strptime(current_first_login, '%Y-%m-%d %H:%M:%S')
                            if datetime.now() - first_login_dt < timedelta(hours=24):
                                is_valid = True
                        except:
                            is_valid = False

                    if is_valid:
                        if needs_update:
                            conn.update(worksheet="Users", data=df)
                        
                        st.session_state['logged_in'] = True
                        st.session_state['user_id'] = uid
                        st.rerun()
                    else:
                        st.error("IDまたはパスワードが間違っています")
                else:
                    st.error("IDまたはパスワードが間違っています")
            except Exception as e:
                st.error(f"システムエラー: {e}")

# ==========================================
# メイン処理フロー
# ==========================================

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    login()
else:
    # --- メインアプリ画面 ---
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"User: **{st.session_state['user_id']}**")
    with col2:
        if st.button("ログアウト", key="logout_btn", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    st.markdown("---")
    st.title("🤖 画像解析")
    
    with st.container(border=True):
        st.write("📸 **解析する画像を選択**")
        uploaded_file = st.file_uploader("", type=['png', 'jpg', 'jpeg'], label_visibility="collapsed")

    if uploaded_file:
        st.image(uploaded_file, caption='プレビュー', use_container_width=True)
        
        if st.button("🚀 解析を開始する", type="primary", use_container_width=True):
            
            with st.status("実行中...", expanded=True) as status:
                
                # A. Geminiで解析 (Drive保存より先に実行)
                status.write("✨ 画像を解析中...")
                gemini_success = False
                try:
                    bytes_data = uploaded_file.getvalue()
                    image_parts = [{"mime_type": uploaded_file.type, "data": bytes_data}]
                    prompt = "この画像を詳しく解析し、何が写っているか日本語で説明してください。"
                    response = model.generate_content([prompt, image_parts[0]])
                    analysis_text = response.text
                    gemini_success = True
                except Exception as e:
                    st.error(f"Gemini解析エラー: {e}")

                # B. Driveへ保存 (失敗しても解析結果は出す)
                drive_link = None
                if gemini_success:
                    status.write("📂 Driveへバックアップ保存中...")
                    drive_link = upload_to_drive(uploaded_file, uploaded_file.name)
                    
                    if drive_link:
                        status.write("✅ 保存完了")
                    else:
                        status.write("⚠️ Drive保存スキップ (容量制限など)")
                
                # 完了処理
                status.update(label="完了!", state="complete", expanded=False)
                
                if gemini_success:
                    st.success("解析結果")
                    st.markdown(analysis_text)
                    
                    if drive_link:
                        st.link_button("📂 保存された画像を開く (Drive)", drive_link, use_container_width=True)
                    else:
                        st.caption("※今回は画像ファイルはDriveに保存されませんでしたが、解析は成功しました。")