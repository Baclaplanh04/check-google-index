import streamlit as st
import pandas as pd
import requests
import time
import re
from io import BytesIO
from datetime import datetime, timedelta
from urllib.parse import quote_plus

st.set_page_config(page_title="Kiểm tra Google Index - Profile", layout="centered")

st.title("Kiểm tra Google Index cho danh sách Profile")
st.markdown(
    "Tải lên file `.xlsx` chứa danh sách URL (bắt đầu từ dòng 3). Ứng dụng sẽ kiểm tra từng URL xem có được Google index hay không, "
    "và (nếu có) lấy ngày cached để xác định có index trong 30 ngày qua hay không."
)

# ====== UPLOAD FILE ======
uploaded_file = st.file_uploader("Chọn file Excel (.xlsx)", type=["xlsx"])

# ====== CÀI ĐẶT ======
st.sidebar.header("Cài đặt kiểm tra")
delay = st.sidebar.number_input("Delay giữa mỗi request (giây)", min_value=0.5, value=2.0, step=0.5)
limit_urls = st.sidebar.number_input("Giới hạn tối đa URLs (để chạy 1 lần)", min_value=1, value=1000, step=1)
user_agent = st.sidebar.selectbox("User-Agent mẫu", [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/118.0 Safari/537.36",
])

headers = {"User-Agent": user_agent}

# ====== HÀM CHÍNH ======
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


# ====== XỬ LÝ FILE ======
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        st.stop()

    # Tìm cột chứa URL (tên gần giống 'profile', 'url', hoặc 'link')
    col_candidates = [c for c in df.columns if re.search(r'profile|url|link', c, re.I)]

    if not col_candidates:
        st.error("Không tìm thấy cột chứa URL (ví dụ: Profile, URL, Link). Vui lòng kiểm tra lại file Excel.")
        st.stop()

    col_name = col_candidates[0]
    profiles = df[col_name].dropna().tolist()[:limit_urls]

    if not profiles:
        st.error("Không có URL nào trong file Excel.")
        st.stop()

    st.success(f"Tìm thấy {len(profiles)} URL. (Sẽ xử lý tối đa {limit_urls} URL theo cài đặt.)")

    # ====== CHẠY KIỂM TRA ======
    results = []
    progress = st.progress(0)
    status_text = st.empty()

    for i, url in enumerate(profiles):
        status_text.text(f"Đang kiểm tra {i+1}/{len(profiles)}: {url}")
        try:
            indexed, html = is_indexed(url, headers)
            cache_date = google_cache_date(url, headers) if indexed else None
            results.append({
                "URL": url,
                "Đã Index": "✅ Có" if indexed else "❌ Không",
                "Ngày Cache": cache_date if cache_date else "-"
            })
        except Exception as e:
            results.append({"URL": url, "Đã Index": "⚠️ Lỗi", "Ngày Cache": str(e)})
        progress.progress((i + 1) / len(profiles))
        time.sleep(delay)

    # ====== HIỂN THỊ KẾT QUẢ ======
    st.subheader("Kết quả kiểm tra")
    result_df = pd.DataFrame(results)
    st.dataframe(result_df, use_container_width=True)

    # Tải kết quả Excel
    output = BytesIO()
    result_df.to_excel(output, index=False)
    st.download_button(
        label="📥 Tải kết quả về (.xlsx)",
        data=output.getvalue(),
        file_name="ket_qua_google_index.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.sidebar.markdown("---")
st.sidebar.info("Ứng dụng sử dụng truy vấn Google (miễn phí). Nếu bạn muốn kết quả ổn định hơn, cân nhắc dùng SerpAPI.")
