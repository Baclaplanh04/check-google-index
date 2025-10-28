import streamlit as st
import pandas as pd
import requests
import time
import re
from io import BytesIO
from datetime import datetime
from urllib.parse import quote_plus

# =============== CẤU HÌNH GIAO DIỆN ===============
st.set_page_config(page_title="Kiểm tra Google Index - Profile", layout="centered")

st.title("🕵️‍♂️ Kiểm tra Google Index cho danh sách Profile")
st.markdown("""
Ứng dụng này giúp bạn kiểm tra xem các URL trong file Excel có được Google index hay không,  
và nếu có thì có **index trong 30 ngày qua** hay không.
""")

# =============== UPLOAD FILE ===============
uploaded_file = st.file_uploader("📤 Tải lên file Excel (.xlsx)", type=["xlsx"])

# =============== CÀI ĐẶT ===============
st.sidebar.header("⚙️ Cài đặt kiểm tra")
delay = st.sidebar.number_input("⏱ Delay giữa mỗi lần kiểm tra (giây)", min_value=0.5, value=2.0, step=0.5)
limit_urls = st.sidebar.number_input("🔢 Giới hạn số URL kiểm tra", min_value=1, value=1000, step=1)
user_agent = st.sidebar.selectbox("🧭 Chọn User-Agent", [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/118.0 Safari/537.36",
])
headers = {"User-Agent": user_agent}


# =============== HÀM KIỂM TRA INDEX ===============
def is_indexed(url, headers):
    """Kiểm tra xem URL có được Google index hay không (chính xác hơn)."""
    query = f"site:{url}"
    try:
        resp = requests.get("https://www.google.com/search?q=" + quote_plus(query), headers=headers, timeout=20)
        html = resp.text.lower()
    except Exception as e:
        return False, f"Lỗi request: {e}"

    # Kiểm tra CAPTCHA / chặn tạm thời
    if "unusual traffic" in html or "recaptcha" in html:
        return False, "⚠️ Google chặn truy cập tạm thời (CAPTCHA)."

    # Nếu có khối kết quả tìm kiếm -> coi như có index
    if re.search(r'class="g"|id="search"|kết quả|about [\d,]+ results|có khoảng', html):
        return True, html

    # Nếu có thông báo không có kết quả
    if "did not match any documents" in html or "no results found" in html or "không tìm thấy kết quả" in html:
        return False, html

    # Trường hợp mặc định
    return False, html


def google_cache_date(url, headers):
    """Lấy ngày cached page từ Google (nếu có)."""
    q = f"cache:{url}"
    try:
        r = requests.get("https://www.google.com/search?q=" + quote_plus(q), headers=headers, timeout=20)
        text = r.text
    except:
        return None

    match = re.search(
        r"As it appeared on (\w+ \d{1,2}, \d{4})|Lưu trong bộ nhớ cache.*?(\d{1,2}) tháng (\d{1,2}), (\d{4})",
        text, re.I
    )
    if match:
        try:
            if match.group(1):
                return datetime.strptime(match.group(1), "%B %d, %Y").strftime("%d/%m/%Y")
            else:
                d, m, y = match.group(2), match.group(3), match.group(4)
                return f"{int(d):02d}/{int(m):02d}/{y}"
        except:
            return None
    return None


# =============== XỬ LÝ FILE EXCEL ===============
if uploaded_file:
    header_row = st.number_input("📄 Dòng chứa tiêu đề (ví dụ: 1 hoặc 3)", min_value=1, value=1, step=1)
    try:
        df = pd.read_excel(uploaded_file, header=header_row - 1)
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        st.stop()

    # Tìm cột chứa URL (Profile/URL/Link)
    col_candidates = [c for c in df.columns if re.search(r'profile|url|link', str(c), re.I)]
    if not col_candidates:
        st.error("❌ Không tìm thấy cột chứa URL (ví dụ: Profile, URL, Link). Vui lòng kiểm tra lại file Excel.")
        st.stop()

    col_name = col_candidates[0]
    profiles = df[col_name].dropna().tolist()[:limit_urls]

    if not profiles:
        st.error("Không có URL nào trong file Excel.")
        st.stop()

    st.success(f"Tìm thấy {len(profiles)} URL. (Sẽ kiểm tra tối đa {limit_urls} URL.)")

    # =============== CHẠY KIỂM TRA ===============
    results = []
    progress = st.progress(0)
    status_text = st.empty()

    for i, url in enumerate(profiles):
        status_text.text(f"🔍 Đang kiểm tra {i+1}/{len(profiles)}: {url}")
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

    # =============== HIỂN THỊ KẾT QUẢ ===============
    st.subheader("📊 Kết quả kiểm tra")
    result_df = pd.DataFrame(results)
    st.dataframe(result_df, use_container_width=True)

    # Xuất file Excel
    output = BytesIO()
    result_df.to_excel(output, index=False)
    st.download_button(
        label="📥 Tải kết quả về (.xlsx)",
        data=output.getvalue(),
        file_name="ket_qua_google_index.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.sidebar.markdown("---")
st.sidebar.info("💡 Mẹo: Nếu bị báo 'Không có URL', hãy kiểm tra lại dòng tiêu đề hoặc tên cột (Profile/URL/Link).")
