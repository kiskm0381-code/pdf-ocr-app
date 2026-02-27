import streamlit as st
import google.generativeai as genai
from docx import Document
import io
from datetime import datetime
import tempfile
import os

# --- ページ設定 ---
st.set_page_config(page_title="PDF文字起こし＆Word統合アプリ", layout="centered")

# --- セッション状態の初期化（ログイン状態の保持） ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# --- パスワード認証画面 ---
if not st.session_state["authenticated"]:
    st.title("🔒 アクセス制限")
    st.write("このアプリを利用するには合言葉を入力してください。")
    
    # Streamlit Secretsから合言葉を取得（クラウド上で後から設定）
    correct_password = st.secrets.get("APP_PASSWORD", "default_password")
    
    password_input = st.text_input("合言葉", type="password")
    
    if st.button("ログイン", type="primary"):
        if password_input == correct_password:
            st.session_state["authenticated"] = True
            st.rerun() # 画面をリロードしてメイン処理へ進む
        else:
            st.error("合言葉が間違っています。")
    
    # 認証されるまではこれ以降のコードを実行しない
    st.stop()

# ==========================================
# これ以降は認証成功時のみ表示・実行される処理
# ==========================================

st.title("📄 PDF文字起こし＆Word統合ツール")
st.write("スキャンしたPDFのテキストを抽出し、Wordファイルに書き出します。")

# SecretsからAPIキーを取得
api_key = st.secrets.get("GEMINI_API_KEY")
if not api_key:
    st.error("システムエラー: APIキーが設定されていません。管理者に連絡してください。")
    st.stop()

genai.configure(api_key=api_key)

# --- メイン画面：ファイルアップロード ---
st.subheader("1. ファイルのアップロード")
uploaded_pdf = st.file_uploader("PDFファイルをドラッグ＆ドロップ", type=["pdf"])
uploaded_word = st.file_uploader("統合したいWordファイル（任意）", type=["docx"])

# --- 処理実行 ---
st.subheader("2. 文字起こしの実行")
if st.button("文字起こしを開始", type="primary"):
    if not uploaded_pdf:
        st.error("PDFファイルをアップロードしてください。")
        st.stop()

    with st.spinner("AIがPDFを読み取っています...（数分かかる場合があります）"):
        try:
            # PDFを一時ファイルとして保存
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(uploaded_pdf.getvalue())
                tmp_pdf_path = tmp_pdf.name

            # Gemini APIへファイルをアップロード
            sample_file = genai.upload_file(path=tmp_pdf_path, display_name="uploaded_document")
            
            # モデルの初期化とテキスト抽出
            model = genai.GenerativeModel(model_name="gemini-3-flash")
            prompt = """
            このPDF文書の文字起こしを行ってください。
            以下のルールを厳守すること：
            - 見出しや段落の構造を維持すること。
            - 表が含まれている場合は、Markdown形式の表として綺麗に出力すること。
            - 余計な挨拶や前置きは出力せず、抽出したテキストのみを出力すること。
            """
            response = model.generate_content([sample_file, prompt])
            extracted_text = response.text

            # API上のファイルを削除（クリーンアップ）
            genai.delete_file(sample_file.name)
            os.remove(tmp_pdf_path)

            st.success("文字起こしが完了しました！")
            
            # --- プレビュー表示 ---
            st.markdown("### 抽出結果プレビュー")
            st.text_area("必要に応じてここで内容を確認できます", extracted_text, height=300)

            # --- Wordファイルの生成/追記 ---
            if uploaded_word:
                doc = Document(uploaded_word)
                doc.add_page_break() # 末尾に改ページを追加
                doc.add_heading("以下、追加抽出データ", level=1)
            else:
                doc = Document()
                doc.add_heading("文字起こし結果", level=1)

            # 抽出テキストをWordに書き込み
            doc.add_paragraph(extracted_text)

            # メモリ上にWordファイルを保存（ダウンロード用）
            word_io = io.BytesIO()
            doc.save(word_io)
            word_io.seek(0)

            # --- ダウンロードボタンの生成 ---
            st.subheader("3. データのダウンロード")
            today_str = datetime.now().strftime("%Y%m%d")
            original_name = uploaded_pdf.name.replace(".pdf", "")
            download_filename = f"{today_str}_{original_name}_抽出結果.docx"

            st.download_button(
                label=f"📥 {download_filename} をダウンロード",
                data=word_io,
                file_name=download_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

        except Exception as e:

            st.error(f"エラーが発生しました: {e}")
