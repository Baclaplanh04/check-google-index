import streamlit as st
import pandas as pd
import requests
import time
import re
from io import BytesIO
from datetime import datetime
from urllib.parse import quote_plus

# ======================
# CẤU HÌNH GIAO DIỆN
# ======================
st.set_page_config(page_title="Kiểm tra Google Index - Profile", layout="centered")

st.title("🧭 Kiểm tra Google Index cho danh sách Profile")
st.markdown("""
Tải lên file **.xlsx** chứa cột **Profile** (bắt đầu từ dòng 3).  
Ứng dụng sẽ kiểm tra từng URL xem có được Google index hay không và (nếu có) lấy ngày cached để xác định có index trong 30 ngày qua hay không.
""")

# ======================
# CÀI ĐẶT NGƯỜI DÙNG
# ======================
delay = st.sidebar.number_input("⏱️ Delay giữa mỗi request (giây)", min_value=1.0, max_value=10.0, value=2.0, step=0.5)
limit = st.sidebar.number_input("🔢 Giới hạn tối đa URLs (để chạy 1 lần)", min_value=1, max_value=1000, value=1000, step=1)
user_agent = st.sidebar.selectbox("🧩 User-Agent mẫu", [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)"
])

st.sidebar.info("Ứng dụng sử dụng truy vấn Google (miễn phí). Nếu bạn muốn kết quả ổn định hơn, cần cân nhắc dùng SerpAPI.")


# ======================
# HÀM KIỂM TRA INDEX
# ======================
def is_indexed(url, headers):
    """Kiểm tra xem URL có được Google index hay không."""
    r = requests.get("https://www.google.com/search?q=" + quote_plus(url), headers=headers, timeout=20)
    text = r.text

    # Nếu có kết quả thống kê số lượng -> có thể đã index
    if re.search(r"results?\s?\d|About [\d,]+ results|Kết quả|Có khoảng", text, re.I):
        return True, text

    # Nếu có thông báo "did not match any documents" -> chưa index
    if re.search(r"did not match any documents|No results found|Không tìm thấy kết quả|không tìm thấy", text, re.I):
        return False, text

    # Nếu có khối kết quả (class="g") -> có thể index
    if 'class="g"' in text or 'id="search"' in text:
        return True, text

    # Mặc định là chưa index
    return False, text


# ======================
# HÀM LẤY NGÀY CACHE
# ======================
def google_cache_date(url, headers):
    """Dùng cache:URL để lấy ngày cached page và parse date (nếu có)."""
    q = f"cache:{url}"
    url_cache = "https://www.google.com/search?q=" + quote_plus(q)
    r = requests.get(url_cache, headers=headers, timeout=20)
    text = r.text

    # Tìm ngày tháng trong nội dung cache (dạng tiếng Anh hoặc Việt)
    match = re.search(
        r"As it appeared on (\w+ \d{1,2}, \d{4})|Lưu trong bộ nhớ cache.*?(\d{1,2}) tháng (\d{1,2}), (\d{4})",
        text,
        re.I
    )

    if match:
        try:
            if match.group(1):
                # English format
                return datetime.strptime(match.group(1), "%B %d, %Y").strftime("%d/%m/%Y")
            else:
                # Vietnamese format
                d, m, y = match.group(2), match.group(3), match.group(4)
                return f"{int(d):02d}/{int(m):02d}/{y}"
        except:
            return None

    return None


# ======================
# XỬ LÝ FILE NGƯỜI DÙNG
# ======================
uploaded_file = st.file_uploader("📂 Chọn file Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        st.stop()

    if 'Profile' not in df.columns:
        st.error("File Excel phải có cột 'Profile' chứa danh sách URL cần kiểm tra.")
        st.stop()

    profiles = df['Profile'].dropna().tolist()
    profiles = profiles[:limit]

    st.success(f"Tìm thấy {len(profiles)} URL. (Sẽ xử lý tối đa {limit} URL theo cài đặt.)")

    if st.button("🚀 Bắt đầu kiểm tra"):
        headers = {"User-Agent": user_agent}
        results = []

        progress = st.progress(0)
        status_text = st.empty()

        for i, url in enumerate(profiles, start=1):
            status_text.text(f"Đang kiểm tra {i}/{len(profiles)}: {url}")

            try:
                indexed, text = is_indexed(url, headers)
                cached_date = google_cache_date(url, headers) if indexed else None

                results.append({
                    "URL": url,
                    "Đã index": "✅ Có" if indexed else "❌ Không",
                    "Ngày cache": cached_date if cached_date else "",
                })

            except Exception as e:
                results.append({
                    "URL": url,
                    "Đã index": "⚠️ Lỗi",
                    "Ngày cache": str(e),
                })

            progress.progress(i / len(profiles))
            time.sleep(delay)

        st.success("🎉 Hoàn tất kiểm tra!")
        result_df = pd.DataFrame(results)

        # Xuất kết quả
        output = BytesIO()
        result_df.to_excel(output, index=False)
        st.download_button("📥 Tải kết quả Excel", data=output.getvalue(), file_name="indexed_results.xlsx")
