# app.py
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
st.markdown("Tải lên file `.xlsx` chứa cột **Profile** (bắt đầu từ dòng 3). Ứng dụng sẽ kiểm tra từng URL xem có được Google index không và (nếu có) lấy ngày cached để xác định có index trong 30 ngày qua hay không.")

# Sidebar settings
st.sidebar.header("Cài đặt kiểm tra")
delay = st.sidebar.number_input("Delay giữa mỗi request (giây)", min_value=1.0, max_value=10.0, value=2.0, step=0.5, help="Tăng delay nếu bị chặn bởi Google.")
max_urls = st.sidebar.number_input("Giới hạn tối đa URLs (để chạy 1 lần)", min_value=10, max_value=1000, value=1000, step=10)
user_agent = st.sidebar.selectbox("User-Agent mẫu", (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)"
    " Version/16.0 Safari/605.1.15"
))
st.sidebar.markdown("---")
st.sidebar.markdown("**Lưu ý:** Ứng dụng sử dụng truy vấn Google (miễn phí). Nếu bạn muốn kết quả ổn định hơn, cân nhắc dùng SerpAPI.")

uploaded_file = st.file_uploader("Chọn file Excel (.xlsx)", type=["xlsx"])
start_button = st.button("Bắt đầu kiểm tra")

def extract_profile_urls(df):
    # attempt to find 'Profile' column (case-insensitive)
    for col in df.columns:
        if str(col).strip().lower() == "profile":
            return df[col].astype(str).dropna().tolist()
    # fallback: try column B if exists
    if df.shape[1] >= 2:
        return df.iloc[:,1].astype(str).dropna().tolist()
    return []

def google_search_site(url, headers):
    """
    Check if 'site:url' returns results. Return tuple (indexed_bool, snippet_html).
    """
    q = f"site:{url}"
    url_search = "https://www.google.com/search?q=" + quote_plus(q)
    r = requests.get(url_search, headers=headers, timeout=20)
    text = r.text
    # Quick heuristic: if results stats exists -> probably indexed
    # results stats pattern: "About 1,230 results" or localized
    if re.search(r"(?i)result(s)? \d|(?i)About [\d,]+ results|(?i)Kết quả|(?i)Có khoảng", text):
        return True, text
    # If "did not match any documents" or "Không tìm thấy kết quả" -> not indexed
    if re.search(r"did not match any documents|No results found|Không tìm thấy kết quả|không tìm thấy", text, re.I):
        return False, text
    # fallback: check if there are result blocks (class="g")
    if 'class="g"' in text or 'id="search"' in text:
        return True, text
    return False, text

def google_cache_date(url, headers):
    """
    Use 'cache:URL' operator to get cached page and parse date if present.
    Returns date string or None.
    """
    q = f"cache:{url}"
    url_cache = "https://www.google.com/search?q=" + quote_plus(q)
    r = requests.get(url_cache, headers=headers, timeout=20)
    text = r.text
    # Search phrases like "It is a snapshot of the page as it appeared on Jun 1, 2025" (English)
    m = re.search(r"snapshot of the page as it appeared on ([A-Za-z0-9, ]+)\.", text)
    if m:
        return m.group(1).strip()
    # Localized Vietnamese pattern sometimes: "Bản sao lưu trang vào ngày 1 tháng 6 năm 2025"
    m2 = re.search(r"ngày\s+([0-9]{1,2}\s+tháng\s+[0-9]{1,2}\s+năm\s+[0-9]{4})", text)
    if m2:
        return m2.group(1).strip()
    # Another approach: look for "Cached" link block and attempt to extract meta time
    m3 = re.search(r"(?i)Cached</a>.*?>([^<>]{10,80})<", text, re.S)
    if m3:
        txt = m3.group(1).strip()
        # Try to find a date-like substring
        date_m = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", txt)
        if date_m:
            return date_m.group(1)
    return None

if uploaded_file and start_button:
    try:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        st.stop()

    urls = extract_profile_urls(df)
    if len(urls) == 0:
        st.error("Không tìm thấy cột 'Profile'. Vui lòng đảm bảo file có cột 'Profile' (hoặc URL ở cột B).")
        st.stop()

    urls = [u.strip() for u in urls if u.strip() != ""]
    st.success(f"Tìm thấy {len(urls)} URL. (Sẽ xử lý tối đa {int(max_urls)} URL theo cài đặt.)")
    urls = urls[:int(max_urls)]

    # Prepare output DataFrame
    out_rows = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    headers = {"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"}

    total = len(urls)
    for i, u in enumerate(urls, start=1):
        status_text.info(f"Đang kiểm tra {i}/{total}: {u}")
        try:
            indexed, snippet = google_search_site(u, headers)
        except Exception as e:
            indexed = False
            snippet = ""
            st.warning(f"Lỗi khi truy vấn Google cho {u}: {e}")

        cached_date = None
        if indexed:
            # try to get cached date (may fail)
            try:
                cached_date = google_cache_date(u, headers)
            except Exception:
                cached_date = None

        # parse cached_date into ISO if possible
        cached_date_iso = None
        if cached_date:
            # Try multiple date formats
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %B %Y", "%d tháng %m năm %Y"):
                try:
                    dt = datetime.strptime(cached_date, fmt)
                    cached_date_iso = dt.date().isoformat()
                    break
                except Exception:
                    continue
            if not cached_date_iso:
                # last resort: keep raw
                cached_date_iso = cached_date

        in_last_30 = "No"
        if cached_date_iso:
            try:
                if isinstance(cached_date_iso, str):
                    # parse ISO-looking
                    dt = None
                    try:
                        dt = datetime.fromisoformat(cached_date_iso)
                    except Exception:
                        pass
                    # fallback: parse common english formats
                    if not dt:
                        for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %B %Y"):
                            try:
                                dt = datetime.strptime(cached_date_iso, fmt)
                                break
                            except:
                                dt = None
                    if dt:
                        if dt.date() >= (datetime.utcnow().date() - timedelta(days=30)):
                            in_last_30 = "Yes"
                        else:
                            in_last_30 = "No"
                    else:
                        in_last_30 = "Unknown"
                else:
                    in_last_30 = "Unknown"
            except Exception:
                in_last_30 = "Unknown"

        out_rows.append({
            "Profile": u,
            "Indexed": "Yes" if indexed else "No",
            "Cached_Date": cached_date_iso if cached_date_iso else "",
            "Indexed_in_last_30_days": in_last_30
        })

        progress_bar.progress(i/total)
        time.sleep(delay)

    result_df = pd.DataFrame(out_rows)
    st.success("Hoàn thành kiểm tra!")
    st.dataframe(result_df.head(200))

    # prepare download
    towrite = BytesIO()
    result_df.to_excel(towrite, index=False, engine="openpyxl")
    towrite.seek(0)
    st.download_button(label="Tải kết quả (indexed_result.xlsx)", data=towrite, file_name="indexed_result.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.info("Nếu Google chặn (mất kết quả/HTML bất thường), hãy tăng 'Delay' ở thanh bên hoặc chia danh sách lớn thành batch nhỏ.")
