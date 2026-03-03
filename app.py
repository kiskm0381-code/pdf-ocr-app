import streamlit as st
import google.generativeai as genai
from docx import Document
import io
from datetime import datetime
import tempfile
import os
from pypdf import PdfReader # ページ数カウントのために追加

# --- アプリの制限設定（3つの防波堤） ---
MAX_FILE_SIZE_MB = 10  # 1ファイルあたりの最大サイズ(MB)
MAX_FILES = 5          # 1回に処理できる最大ファイル数
MAX_TOTAL_PAGES = 30   # 1回に処理できる合計最大ページ数

# --- ページ設定（wideレイアウト） ---
st.set_page_config(page_title="PDF文字起こし＆Word統合アプリ", layout="wide")

# --- カスタムCSS（不要なUIの完全排除とデザイン調整） ---
st.markdown("""
    <style>
    .main-header {font-size: 2.2rem; font-weight: bold; color: #1E3A8A; margin-bottom: 0.5rem;}
    .sub-header {font-size: 1.1rem; color: #4B5563; margin-bottom: 1rem;}
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .guide-box {background-color: #F3F4F6; padding: 1.5rem; border-radius: 10px; border: 1px solid #E5E7EB;}
    .alert-box {background-color: #FEF2F2; color: #991B1B; padding: 1rem; border-radius: 5px; border: 1px solid #F87171; margin-top: 1rem;}
    </style>
""", unsafe_allow_html=True)

# --- セッション状態の初期化 ---
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

api_key = st.secrets.get("GEMINI_API_KEY")
if not api_key:
    st.error("システムエラー: APIキーが設定されていません。管理者に連絡してください。")
    st.stop()

genai.configure(api_key=api_key)

# --- ヘッダー領域 ---
st.markdown('<div class="main-header">📄 PDF文字起こし＆Word統合ツール</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">スキャンした複数のPDFを一度に高精度でテキスト化し、美しいWordファイルに統合します。</div>', unsafe_allow_html=True)
st.divider()

# --- 画面の分割（左側: 75% 作業エリア, 右側: 25% ガイドエリア） ---
main_col, guide_col = st.columns([3, 1])

# ===== 右側：ご利用ガイドと制限事項 =====
with guide_col:
    st.markdown("""
    <div class="guide-box">
        <h4 style="margin-top: 0;">💡 ご利用ガイド</h4>
        <p><b>STEP 1: PDFのアップロード</b><br>左側の枠に文字起こししたいPDFをドラッグ＆ドロップします。</p>
        <p><b>STEP 2: 統合先Wordの指定（任意）</b><br>既存のファイルの末尾に追記したい場合は右側の枠にアップロードします。</p>
        <p><b>STEP 3: 文字起こしの実行</b><br>「✨ 文字起こしを開始」ボタンを押すと、AIが全自動でテキストを抽出・再構築します。</p>
        <p><b>STEP 4: 確認とダウンロード</b><br>プレビューを確認後、Wordファイルをダウンロードしてください。</p>
    </div>
    """, unsafe_allow_html=True)
    
    # サイト内に制限事項を明記
    st.markdown(f"""
    <div class="alert-box">
        <b>⚠️ システム利用上の制限</b><br>
        安定稼働のため、1回の処理につき以下の制限を設けています。<br>
        ・最大ファイル数: <b>{MAX_FILES} ファイル</b>まで<br>
        ・ファイルサイズ: 1つあたり <b>{MAX_FILE_SIZE_MB}MB</b> まで<br>
        ・合計ページ数: 最大 <b>{MAX_TOTAL_PAGES} ページ</b>まで
    </div>
    """, unsafe_allow_html=True)

# ===== 左側：メイン作業エリア =====
with main_col:
    with st.container():
        st.write("### 1. ファイルのアップロード")
        upload_col1, upload_col2 = st.columns(2)
        with upload_col1:
            uploaded_pdfs = st.file_uploader(f"📂 PDFファイル（最大{MAX_FILES}個）", type=["pdf"], accept_multiple_files=True)
        with upload_col2:
            uploaded_word = st.file_uploader("📝 統合したい既存のWordファイル（任意）", type=["docx"])
            if uploaded_word:
                st.success(f"統合先ファイル: {uploaded_word.name} の末尾に追記します。")

    st.write("### 2. 文字起こしの実行")
    if st.button("✨ 文字起こしを開始", type="primary", use_container_width=True):
        if not uploaded_pdfs:
            st.error("PDFファイルをアップロードしてください。")
            st.stop()

        # 【防波堤1】ファイル数の制限チェック
        if len(uploaded_pdfs) > MAX_FILES:
            st.error(f"⚠️ エラー: アップロードできるファイルは最大 {MAX_FILES} 個までです。（現在: {len(uploaded_pdfs)}個）")
            st.stop()

        total_pages = 0
        with st.spinner("ファイルの要件をチェックしています..."):
            for pdf_file in uploaded_pdfs:
                # 【防波堤2】ファイルサイズの制限チェック
                if pdf_file.size > (MAX_FILE_SIZE_MB * 1024 * 1024):
                    st.error(f"⚠️ エラー: 『{pdf_file.name}』のサイズが {MAX_FILE_SIZE_MB}MB を超えています。")
                    st.stop()
                
                # 【防波堤3】合計ページ数の制限チェック
                try:
                    pdf_reader = PdfReader(pdf_file)
                    total_pages += len(pdf_reader.pages)
                    pdf_file.seek(0) # AIに渡すためにファイルポインタを先頭に戻す
                except Exception as e:
                    st.error(f"⚠️ エラー: 『{pdf_file.name}』の読み取りに失敗しました。破損している可能性があります。")
                    st.stop()

        if total_pages > MAX_TOTAL_PAGES:
            st.error(f"⚠️ エラー: 合計ページ数が上限の {MAX_TOTAL_PAGES} ページを超えています。（現在: 合計 {total_pages} ページ）ファイルを減らして再実行してください。")
            st.stop()

        # --- 以下、文字起こしの本処理 ---
        if uploaded_word:
            doc = Document(uploaded_word)
            doc.add_page_break() 
            doc.add_heading("以下、追加抽出データ", level=1)
        else:
            doc = Document()
            doc.add_heading("文字起こし結果", level=1)

        total_files = len(uploaded_pdfs)
        progress_bar = st.progress(0, text=f"処理を開始します... (0/{total_files})")
        all_extracted_texts = [] 

        try:
            model = genai.GenerativeModel(model_name="gemini-2.5-flash")
            prompt = """
            このPDF文書のテキストを抽出し、人間が最も読みやすい論理的な構造で再構成してください。
            推測や事実の捏造は一切行わず、文書に記載されている情報のみを使用して、以下のルールを厳密に守ること：
            1. 【論理的な再配置】文書全体の論理的な流れを構築すること。文書の「タイトル（題名）」を特定し、その直後に「目次」ブロックを移動させて配置すること。その後ろに本文を順序良く続けること。
            2. 【文章の結合と整形】段組みやページ分割によって途切れた文章は、意味が通るように1つの文章・段落単位で綺麗に結合すること。文中の不自然な改行や、単語間の不要なスペースはすべて削除し、自然で読みやすい日本語の文章に修正すること。
            3. 【ノイズの排除】ヘッダー（例：「〔社会保険通報〕」）やフッター（例：ページ番号）、本文に関係のない記号などはすべて除外すること。
            4. 【表の高度な再現】表（テーブル）が含まれる場合、元の表の行列構造を極限まで正確に読み取り、必ずMarkdown形式の表として出力すること。テキストの羅列に崩さず、極力元の表に近い視覚的構造を維持すること。
            5. 【出力形式】余計な挨拶や前置きは一切出力せず、整形後のテキストデータのみを出力すること。
            """

            for i, uploaded_pdf in enumerate(uploaded_pdfs):
                progress_bar.progress((i) / total_files, text=f"AIが読み取っています... {i+1}/{total_files}件目: {uploaded_pdf.name}")
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                    tmp_pdf.write(uploaded_pdf.getvalue())
                    tmp_pdf_path = tmp_pdf.name

                sample_file = genai.upload_file(path=tmp_pdf_path, display_name="uploaded_document")
                response = model.generate_content([sample_file, prompt])
                extracted_text = response.text

                genai.delete_file(sample_file.name)
                os.remove(tmp_pdf_path)
                
                doc.add_heading(f"【ファイル名：{uploaded_pdf.name}】", level=2)
                doc.add_paragraph(extracted_text)
                
                if i < total_files - 1:
                    doc.add_page_break()

                all_extracted_texts.append(f"--- 📄 {uploaded_pdf.name} ---\n{extracted_text}\n")

            progress_bar.progress(1.0, text=f"処理完了！全 {total_files} 件の文字起こしが終了しました。")
            st.success("すべての文字起こしが完了しました！")
            
            st.markdown("### 📝 抽出結果プレビュー")
            with st.expander("プレビューを確認（クリックで展開）", expanded=True):
                st.text_area("抽出されたテキストデータ:", "\n".join(all_extracted_texts), height=350)

            word_io = io.BytesIO()
            doc.save(word_io)
            word_io.seek(0)

            st.divider()
            st.subheader("3. データのダウンロード")
            st.write("下のボタンを押すと、お手元のPCやGoogle DriveにWordファイルとして保存できます。")
            
            today_str = datetime.now().strftime("%Y%m%d")
            if total_files == 1:
                original_name = uploaded_pdfs[0].name.replace(".pdf", "")
                download_filename = f"{today_str}_{original_name}_抽出結果.docx"
            else:
                download_filename = f"{today_str}_複数ファイル一括抽出結果_{total_files}件.docx"

            st.download_button(
                label=f"📥 {download_filename} をダウンロード",
                data=word_io,
                file_name=download_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary"
            )

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
