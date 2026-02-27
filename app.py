import streamlit as st
import google.generativeai as genai
from docx import Document
import io
from datetime import datetime

# --- ページ基本設定（美しいUIのベース） ---
st.set_page_config(page_title="業務フロー自動生成アプリ", layout="wide", initial_sidebar_state="expanded")

# --- セッション状態の初期化（ログイン状態の保持） ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# --- パスワード認証画面 ---
if not st.session_state["authenticated"]:
    st.title("🔒 アクセス制限")
    st.write("このアプリを利用するには合言葉を入力してください。")
    
    correct_password = st.secrets.get("APP_PASSWORD", "default_password")
    password_input = st.text_input("合言葉", type="password")
    
    if st.button("ログイン", type="primary"):
        if password_input == correct_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("合言葉が間違っています。")
    st.stop()

# ==========================================
# これ以降は認証成功時のみ表示・実行される処理
# ==========================================

# --- APIキー設定 ---
api_key = st.secrets.get("GEMINI_API_KEY")
if not api_key:
    st.error("システムエラー: APIキーが設定されていません。")
    st.stop()
genai.configure(api_key=api_key)

# --- カスタムCSS（視認性の向上） ---
st.markdown("""
    <style>
    .main-header {font-size: 2.5rem; font-weight: bold; color: #1E3A8A; margin-bottom: 0.5rem;}
    .sub-header {font-size: 1.2rem; color: #4B5563; margin-bottom: 2rem;}
    </style>
""", unsafe_allow_html=True)

# --- サイドバー：検索・設定エリア ---
with st.sidebar:
    st.header("🔍 フロー検索＆設定")
    search_query = st.text_input("過去のフローを検索（キーワード）")
    if search_query:
        st.info(f"「{search_query}」の検索結果（※今後のデータベース連携アップデートで実装予定です）")
    
    st.divider()
    st.write("⚙️ 出力設定")
    output_format = st.radio("希望する出力形式", ["Word (.docx)", "Markdown (.md)"])
    st.caption("※サーバー依存のレイアウト崩れを防ぐため、編集・再利用が容易な形式に絞っています。")

# --- メインコンテンツ ---
st.markdown('<div class="main-header">🚀 業務フロー作成ツール</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">直感的な操作で、誰でも美しいマニュアルを瞬時に生成します。</div>', unsafe_allow_html=True)

# 構造的アップデートA: 入力エリアの整理
with st.container():
    col1, col2 = st.columns([2, 1])
    with col1:
        task_name = st.text_input("業務の名称", placeholder="例：新入社員オンボーディング手順")
        task_details = st.text_area(
            "業務の具体的な手順や要件", 
            height=150, 
            placeholder="例：\n・PCセットアップ\n・社内システムのID発行\n・就業規則の読み合わせ"
        )
    with col2:
        st.info("💡 箇条書きでラフに入力するだけで、AIが「目的」「事前準備」「手順」「注意点」を含む論理的な構造に再編成します。")

# 構造的アップデートB: アクションとプレビューの分離
st.divider()
if st.button("✨ 業務フローを自動生成", type="primary", use_container_width=True):
    if not task_name:
        st.error("業務の名称を入力してください。")
    else:
        with st.spinner("AIが最適なフローを構築中..."):
            try:
                # モデルの初期化（Gemini 2.5 Flashを採用）
                model = genai.GenerativeModel(model_name="gemini-2.5-flash")
                
                # 業務フロー構築に特化した強力なプロンプト
                prompt = f"""
                あなたはプロの業務コンサルタントです。以下の情報をもとに、誰が読んでも迷わず実行できる、論理的で美しい業務フロー（マニュアル）を作成してください。

                【業務の名称】
                {task_name}

                【業務の要件・手順（ラフ）】
                {task_details}

                【厳守する出力ルール】
                1. 以下の構成で出力すること：
                   - タイトル（大見出し）
                   - 業務の目的（簡潔に）
                   - 必要な準備・前提条件
                   - 実行手順（時系列でステップバイステップに）
                   - 注意点・イレギュラー対応
                2. Markdown形式を使用し、見出し（##）、箇条書き（-）、太字（**）を駆使して視覚的に美しく整理すること。
                3. 手順が不足している部分があっても、一般的なビジネスのベストプラクティスに基づいてAIが自然に補完・提案すること。
                4. 余計な挨拶や説明は省き、成果物（マニュアル本体）のみを出力すること。
                """
                
                response = model.generate_content(prompt)
                
                # セッションに結果を保存
                st.session_state['generated_workflow'] = response.text
                st.session_state['task_name'] = task_name
                st.success("フローの生成が完了しました！")
                
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

# 構造的アップデートC: 美しいプレビューとダウンロードへの導線
if 'generated_workflow' in st.session_state:
    st.markdown("### 📝 生成されたフローのプレビュー")
    with st.expander("プレビューを確認 / 編集（クリックで展開）", expanded=True):
        st.markdown(st.session_state['generated_workflow'])
    
    st.markdown("### 📥 データの保存")
    st.write("下のボタンを押すと、ブラウザ経由で任意の場所（Google Drive等）に保存できます。")
    
    today_str = datetime.now().strftime("%Y%m%d")
    safe_task_name = st.session_state['task_name'].replace("/", "_").replace("\\", "_")
    
    if output_format == "Word (.docx)":
        doc = Document()
        doc.add_heading(f"業務フロー: {st.session_state['task_name']}", level=1)
        doc.add_paragraph(st.session_state['generated_workflow'])
        
        word_io = io.BytesIO()
        doc.save(word_io)
        word_io.seek(0)
        
        st.download_button(
            label=f"📥 Wordでダウンロード",
            data=word_io,
            file_name=f"{today_str}_{safe_task_name}_業務フロー.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        file_content = st.session_state['generated_workflow'].encode('utf-8')
        st.download_button(
            label=f"📥 Markdownでダウンロード",
            data=file_content,
            file_name=f"{today_str}_{safe_task_name}_業務フロー.md",
            mime="text/markdown"
        )
