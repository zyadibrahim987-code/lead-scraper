# Lead Scraper — أداة تجمع بيانات الشركات والمتاجر الإلكترونية

بتطلع: **الاسم - الرقم - واتساب - الإيميل - العنوان - الموقع - منصة المتجر - فيسبوك - انستجرام - تيك توك - لينكدإن - X - يوتيوب - سناب** + التقييم ورابط جوجل ماب. الملف بيتحفظ Excel أو CSV.

## الواجهة (الأسهل)
- ويندوز: دبل كليك على `run.bat`
- ماك/لينكس: `./run.sh` أو `streamlit run app.py`

هتفتح في المتصفح على http://localhost:8501 ← حط المفاتيح في الشريط الجانبي ← اكتب النشاط والمكان ← ابدأ ← نزّل Excel.

## التشغيل من الترمينال
```bash
pip install -r requirements.txt
export GOOGLE_PLACES_API_KEY="..."   # Google Maps
export SERPER_API_KEY="..."          # بحث جوجل + السوشيال
python lead_scraper.py -q "متجر ملابس" -l "القاهرة" --max 60 -o cairo.xlsx
```

## المفاتيح
| المصدر | منين | التكلفة |
|---|---|---|
| Google Maps | console.cloud.google.com ← فعّل **Places API (New)** ← Credentials | فيه رصيد مجاني شهري من جوجل |
| بحث جوجل + السوشيال | serper.dev | 2500 بحث مجاني |

## أمثلة
- مواقع عندك جاهزة: `python lead_scraper.py --urls urls.txt`
- جوجل ماب بس: `--sources maps`
- اللي ليهم رقم بس: `--only-with-phone`
- من غير زيارة المواقع (أسرع): `--no-enrich`
