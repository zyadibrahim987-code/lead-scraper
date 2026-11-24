"""
واجهة Lead Scraper
التشغيل:  streamlit run app.py
"""
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

import lead_scraper as L

st.set_page_config(page_title="Lead Scraper", page_icon="🔎", layout="wide")
st.markdown("""
<style>
  .main .block-container, section[data-testid="stSidebar"] { direction: rtl; text-align: right; }
  [data-testid="stDataFrame"] { direction: ltr; }
</style>""", unsafe_allow_html=True)

st.title("🔎 جمع بيانات الشركات والمتاجر")
st.caption("الاسم - الرقم - واتساب - الإيميل - العنوان - الموقع - السوشيال ميديا")

# ---------------------------------------------------------------- Sidebar
with st.sidebar:
    st.header("🔑 مفاتيح الـ API")
    maps_key = st.text_input("Google Places API Key", value=os.getenv("GOOGLE_PLACES_API_KEY", ""),
                             type="password")
    serper_key = st.text_input("Serper API Key", value=os.getenv("SERPER_API_KEY", ""), type="password")
    st.caption("جوجل ماب: console.cloud.google.com ← Places API (New)\n\nالبحث والسوشيال: serper.dev")
    st.divider()
    st.header("⚙️ إعدادات")
    max_results = st.slider("أقصى عدد نتائج لكل مصدر", 10, 200, 40, step=10)
    do_enrich = st.checkbox("ادخل على موقع كل نشاط وكمّل بياناته", value=True,
                            help="بيجيب الإيميل والواتساب والسوشيال من الموقع نفسه — أبطأ لكن أدق")
    only_phone = st.checkbox("اعرض اللي ليهم رقم أو واتساب بس", value=False)

# ---------------------------------------------------------------- Inputs
tab_search, tab_urls = st.tabs(["🔍 بحث بالنشاط والمكان", "🔗 عندي لينكات مواقع"])
with tab_search:
    c1, c2 = st.columns(2)
    query = c1.text_input("نوع النشاط", placeholder="متجر ملابس / online store / مطعم")
    location = c2.text_input("المكان", placeholder="القاهرة / الرياض / Dubai")
    sources = st.multiselect("المصادر", ["Google Maps", "بحث جوجل + السوشيال"],
                             default=["Google Maps", "بحث جوجل + السوشيال"])
with tab_urls:
    urls_text = st.text_area("لينك في كل سطر", height=150,
                             placeholder="https://store1.com\nstore2.com")

run = st.button("🚀 ابدأ", type="primary", use_container_width=True)

# ---------------------------------------------------------------- Run
if run:
    os.environ["GOOGLE_PLACES_API_KEY"] = maps_key.strip()
    os.environ["SERPER_API_KEY"] = serper_key.strip()
    records = []
    with st.status("جاري جمع البيانات...", expanded=True) as status:
        if query.strip():
            if "Google Maps" in sources:
                if not maps_key:
                    st.warning("تخطي جوجل ماب: مفيش Google Places API Key")
                else:
                    st.write("📍 بدور في جوجل ماب...")
                    r = L.source_google_maps(query, location, max_results)
                    st.write(f"✔ جوجل ماب: {len(r)} نتيجة")
                    records += r
            if "بحث جوجل + السوشيال" in sources:
                if not serper_key:
                    st.warning("تخطي البحث: مفيش Serper API Key")
                else:
                    st.write("🌐 بدور في جوجل وانستجرام وفيسبوك وتيك توك ولينكدإن...")
                    r = L.source_search(query, location, max_results)
                    st.write(f"✔ البحث: {len(r)} نتيجة")
                    records += r
        urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
        if urls:
            records += [{"name": "", "website": u if u.startswith("http") else "https://" + u,
                         "source": "urls"} for u in urls]
            st.write(f"✔ {len(urls)} لينك من عندك")

        if not records:
            status.update(label="مفيش نتائج", state="error")
            st.error("اكتب نوع النشاط والمكان (ومعاهم المفاتيح) أو حط لينكات مواقع.")
            st.stop()

        records = L.dedupe(records)
        if do_enrich:
            n_sites = sum(1 for r in records if r.get("website"))
            st.write(f"🔎 بدخل على {n_sites} موقع وبكمّل البيانات...")
            bar = st.progress(0.0)
            done, out = 0, []
            with ThreadPoolExecutor(8) as ex:
                futs = [ex.submit(L.enrich, r) for r in records]
                for f in as_completed(futs):
                    out.append(f.result())
                    done += 1
                    bar.progress(done / len(futs))
            records = L.dedupe(out)
        if only_phone:
            records = [r for r in records if r.get("phone") or r.get("whatsapp")]
        status.update(label=f"✔ خلصت — {len(records)} نشاط", state="complete", expanded=False)

    st.session_state["records"] = records

# ---------------------------------------------------------------- Results
records = st.session_state.get("records")
if records:
    df = pd.DataFrame(records).reindex(columns=L.FIELDS).fillna("")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("إجمالي", len(df))
    m2.metric("ليهم رقم", int((df["phone"] != "").sum()))
    m3.metric("ليهم إيميل", int((df["email"] != "").sum()))
    m4.metric("ليهم انستجرام", int((df["instagram"] != "").sum()))

    link_cols = {c: st.column_config.LinkColumn(c) for c in
                 ["website", "facebook", "instagram", "tiktok", "linkedin", "twitter",
                  "youtube", "snapchat", "maps_url"]}
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=link_cols, height=500)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        L.save(records, tmp.name)
        xlsx = open(tmp.name, "rb").read()
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ تحميل Excel", xlsx, "leads.xlsx", use_container_width=True,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d2.download_button("⬇️ تحميل CSV", df.to_csv(index=False).encode("utf-8-sig"), "leads.csv",
                       "text/csv", use_container_width=True)
