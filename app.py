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
            
            # モデルの初期化（Gemini 2.5 Flashを適用）
            model = genai.GenerativeModel(model_name="gemini-2.5-flash")
            
            # 物理的順序の絶対遵守と構造認識を強制するプロンプト
            prompt = """
            このPDF文書の高精度な文字起こしを行ってください。
            以下のルールを厳密に守り、AIによる勝手な「順序の入れ替え」や「文脈の推測」を完全に排除してください：

            1. 【絶対的な物理的順序の遵守】ページごとに、上から下へ物理的な配置順序の通りに処理すること。ページをまたいで文章を先読みしたり、目次や注釈などのブロックを文書の末尾に後回しにしたりすることは絶対に禁止する。目次が1ページ目の下部にあるなら、そのまま1ページ目の下部のテキストとして出力すること。
            2. 【段組みの正確な処理】同一ページ内に段組み（2段組みなど）がある場合は、その段組みブロック内においてのみ「右段を上から下へ → 左段を上から下へ」の順序で読むこと。左右の段のテキストを絶対に混ぜないこと。
            3. 【ページ内ブロックの移行】段組みの下に、ページ幅全体を使った別のブロック（目次や表など）がある場合は、段組みを読み終えた直後に、そのまま順序通りに処理を続けること。
            4. 【ノイズの排除】ヘッダー（「〔社会保険通報〕」など）やフッター（ページ番号「- 1 -」など）、欄外の不要なテキストは出力から完全に除外すること。
            5. 【構造の維持】見出し、段落の構造、箇条書きを正確に維持し、表が含まれる場合は必ずMarkdown形式の表（テーブル）として綺麗に出力すること。
            6. 【出力形式】余計な挨拶や前置き、説明は一切出力せず、抽出・構成したテキストデータのみを出力すること。
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
