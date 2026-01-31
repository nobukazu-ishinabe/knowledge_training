import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import io

# ==========================================
# 1. アプリ設定とプロンプト定義 (★ここを編集)
# ==========================================
st.set_page_config(
    page_title="課題解決スキル向上研修", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# ▼▼▼ プロンプト定義エリア ▼▼▼
PROMPT_TEMPLATE = """
# 命令書
あなたは、大手企業の経営企画室に所属する「戦略策定のプロフェッショナル」です。
現在、社員の「課題設定能力（Issue definition）」を養う研修を行っており、受講者が「ゴール（To-Be）」「現在地（As-Is）」「ギャップ（Gap）」を定義した画像をアップロードします。
画像内のテキストを読み取り、認識した内容を提示した上で、その定義品質を厳格に評価・フィードバックしてください。

# コンセプト
「不鮮明な地図では、ゴールには辿り着けない」
（解決策を考える前に、地図＝課題定義が正確かを確認するフェーズです）

# 解析プロセス
1.  **画像認識:** 画像内に書かれているテキストを正確に読み取る。
2.  **要素分類:** 読み取ったテキストを「目的地」「現在地」「ギャップ」に分類する。
3.  **厳格評価:** その定義がビジネスレベル（数値・事実・構造化）に達しているか評価する。

# 出力フォーマット

## 📝 読み取り内容の確認
画像から以下のテキストを認識しました。誤りがないか確認してください。
- **目的地 (Goal):** [画像から読み取ったテキストをそのまま記述]
- **現在地 (Current):** [画像から読み取ったテキストをそのまま記述]
- **ギャップ (Gap):** [画像から読み取ったテキストをそのまま記述]

---

## 🗺️ 課題定義マップの「鮮明度」判定（S/A/B/C）
**判定：[ここにランクを表示]**

> **ランク定義**
> - **S (承認 - Clear):** 座標（数値）が鮮明で、構造的なギャップが特定されている。即座に解決策の検討へ進める。
> - **A (条件付承認 - Good):** 概ね良いが、一部の数値根拠や言語化に甘さが残る。
> - **B (要再設定 - Foggy):** 定性的な表現（形容詞）が多く、このまま進むと遭難するリスクがある。
> - **C (視界不良 - Unclear):** 単なる願望や感想レベル。地図として機能していない。

---

## 🧭 戦略プロフェッショナルからのフィードバック
### 1. 目的地の視認性
[「売上を上げる」等の曖昧さを排し、KGI/KPIなどの数値目標になっているか評価]

### 2. 現在地の正確性
[事実・データに基づいているか、主観や思い込み（解釈）が混ざっていないか評価]

### 3. ギャップの深さ
[表面的な事象ではなく、構造的な真因（ボトルネック）を捉えているか評価]

---

## ✏️ 【修正案】プロが描く「鮮明な地図」
あなたの定義を、ビジネスで通用するレベル（KPI/Factベース）に書き換えるとこうなります：
- **目的地:** [数値を明確にした修正案]
- **現在地:** [客観的事実を用いた修正案]
- **ギャップ:** [構造的な真因を特定した修正案]

## ⚔️ 次のフェーズに進むための「問い」
[この定義が正しいと仮定した上で、解決策（How）を考える前に自問すべき、核心を突く質問を1つ]
"""
# ▲▲▲ プロンプト定義エリア ▲▲▲

# UI調整用CSS
hide_streamlit_style = """
            <style>
            header {visibility: hidden !important;}
            footer {visibility: hidden !important; display: none !important;}
            [data-testid="stDecoration"] {display: none !important;}
            [data-testid="stStatusWidget"] {display: none !important;}
            
            /* Primaryボタン(赤)を青色に上書き */
            button[kind="primary"] {
                background-color: #0068C9 !important;
                border-color: #0068C9 !important;
                color: white !important;
            }
            /* ホバー時の色（少し濃い青） */
            button[kind="primary"]:hover {
                background-color: #0053a0 !important;
                border-color: #0053a0 !important;
                color: white !important;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Gemini設定
if "general" in st.secrets and "gemini_api_key" in st.secrets["general"]:
    genai.configure(api_key=st.secrets["general"]["gemini_api_key"])
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
else:
    st.error("Secrets設定エラー: gemini_api_keyが見つかりません。")

# ==========================================
# 2. 関数定義
# ==========================================

# Google Driveへのアップロード関数
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

        file = service.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        return file.get('webViewLink')
        
    except Exception as e:
        print(f"Drive Upload Error: {e}") 
        return None

# ユーザー情報の取得・更新関数
def get_user_data(conn, username):
    df = conn.read(worksheet="Users", ttl=0)
    
    if 'first_login' not in df.columns:
        df['first_login'] = ""
    if 'feedback_result' not in df.columns:
        df['feedback_result'] = ""
    
    df = df.fillna("")
    
    user_rows = df[df['username'].astype(str) == username]
    
    if not user_rows.empty:
        return df, user_rows.index[0]
    return df, None

# ログイン処理関数
def login():
    st.markdown("### 🔐 研修アプリ ログイン")
    
    with st.form("login_form"):
        uid = st.text_input("ユーザーID")
        password = st.text_input("パスワード", type="password")
        submit = st.form_submit_button("ログイン", use_container_width=True)
        
        if submit:
            conn = st.connection("gsheets", type=GSheetsConnection)
            try:
                df = conn.read(worksheet="Users", ttl=0)
                if 'first_login' not in df.columns: df['first_login'] = ""
                if 'feedback_result' not in df.columns: df['feedback_result'] = ""
                df = df.fillna("")

                match_indices = df.index[
                    (df['username'].astype(str) == uid) & 
                    (df['password'].astype(str) == password)
                ].tolist()
                
                if match_indices:
                    idx = match_indices[0]
                    current_first_login = str(df.at[idx, 'first_login'])
                    
                    is_valid = False
                    needs_update = False
                    
                    if current_first_login == "":
                        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        df.at[idx, 'first_login'] = now_str
                        is_valid = True
                        needs_update = True
                    else:
                        try:
                            first_login_dt = datetime.strptime(current_first_login, '%Y-%m-%d %H:%M:%S')
                            #if datetime.now() - first_login_dt < timedelta(hours=24):
                            if datetime.now() - first_login_dt < timedelta(hours=720):
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
                        st.error("IDまたはパスワードが間違っています（有効期限切れ）")
                else:
                    st.error("IDまたはパスワードが間違っています")
            except Exception as e:
                st.error(f"システムエラー: {e}")

# ==========================================
# 3. メイン処理フロー
# ==========================================

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'is_retry' not in st.session_state:
    st.session_state['is_retry'] = False

if not st.session_state['logged_in']:
    login()
else:
    # --- ログイン後の画面 ---
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df, user_idx = get_user_data(conn, st.session_state['user_id'])
        
        if user_idx is not None:
            saved_feedback = str(df.at[user_idx, 'feedback_result'])
        else:
            saved_feedback = ""
            st.error("ユーザー情報の取得に失敗しました")
            st.stop()
            
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        st.stop()

    # ヘッダー
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"受講者: **{st.session_state['user_id']}**")
    with col2:
        if st.button("ログアウト", key="logout_btn", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state['is_retry'] = False
            st.rerun()
    st.markdown("---")

    # === 画面分岐 ===
    if saved_feedback and not st.session_state['is_retry']:
        st.title("✅ 評価フィードバック")
        st.success("前回の提出に対するAI評価です")
        
        with st.container(border=True):
            st.markdown(saved_feedback)
            
        st.markdown("---")
        st.write("課題を修正して、再度提出する場合は下のボタンを押してください。")
        if st.button("🔄 修正して再提出する", type="primary", use_container_width=True):
            st.session_state['is_retry'] = True
            st.rerun()

    else:
        st.title("📝 課題提出")
        
        with st.container(border=True):
            st.markdown("#### 📌 提出要件")
            st.write("以下の3点が記載された画像をアップロードしてください。")
            st.markdown("""
            1. **目的 (Goal)**：あるべき姿、目指す状態
            2. **現在地 (Current)**：現状の課題、事実
            3. **ギャップ (Gap)**：目的と現在地の間にある問題点、阻害要因
            """)
            with st.expander("👀 記入例を見る（クリックして開く）"):
                st.markdown("""
                **例：チームビルディングの課題**
                * **目的**：若手社員が自発的に意見を出し、活気あるチームにする。
                * **現在地**：会議で発言するのはリーダーだけで、若手は指示待ちになっている。
                * **ギャップ**：若手に自信がなく、間違ったことを言うのを恐れている。心理的安全性がない。
                """)

        st.write("")
        uploaded_file = st.file_uploader("課題ファイルをアップロード", type=['png', 'jpg', 'jpeg'])

        if uploaded_file:
            st.image(uploaded_file, caption='プレビュー', use_container_width=True)
            
            btn_label = "🚀 AI評価を実行する" if not saved_feedback else "🚀 再評価を実行する"
            
            if st.button(btn_label, type="primary", use_container_width=True):
                
                analysis_text = ""
                
                # withブロックの中は「処理中」の表示だけにする
                with st.status("AI講師が評価中...", expanded=True) as status:
                    
                    # A. Gemini解析
                    status.write("🧠 画像を解析し、ロジックを評価中...")
                    
                    try:
                        bytes_data = uploaded_file.getvalue()
                        image_parts = [{"mime_type": uploaded_file.type, "data": bytes_data}]
                        
                        # 定義したプロンプトを使用
                        response = model.generate_content([PROMPT_TEMPLATE, image_parts[0]])
                        
                        analysis_text = response.text
                    except Exception as e:
                        st.error(f"AI解析エラー: {e}")
                        status.update(label="解析エラー", state="error")
                        st.stop()

                    # B. Drive保存
                    status.write("📂 提出履歴を保存中...")
                    drive_link = upload_to_drive(uploaded_file, f"{st.session_state['user_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                    
                    # C. スプレッドシート保存
                    status.write("💾 評価シートを更新中...")
                    try:
                        df.at[user_idx, 'feedback_result'] = analysis_text
                        conn.update(worksheet="Users", data=df)
                    except Exception as e:
                        st.error(f"保存エラー: {e}")
                    
                    status.update(label="評価完了！", state="complete", expanded=False)
                
                # ▼▼▼ 修正箇所: ここをwithブロックの外に出しました ▼▼▼
                st.success("評価が完了しました")
                st.markdown("### 📝 AI講師からのフィードバック")
                st.markdown(analysis_text)
                
                # 再評価フラグをリセット
                st.session_state['is_retry'] = False

