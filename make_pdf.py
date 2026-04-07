from fpdf import FPDF

def make_pdf(filename, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.cell(200, 10, txt=f"{title}", ln=1, align='C')
    pdf.cell(200, 10, txt="ABSTRACT", ln=1)
    pdf.multi_cell(0, 10, txt="This paper explores the underlying mechanisms of novel architectures. We present a dynamic theoretical framework.")
    
    pdf.cell(200, 10, txt="INTRODUCTION", ln=1)
    pdf.multi_cell(0, 10, txt="Recent advances point to new limitations. Therefore, we aim to bridge the gap.")
    
    pdf.cell(200, 10, txt="METHODS", ln=1)
    pdf.multi_cell(0, 10, txt="We used empirical data gathered from 100 participants. The study employs a randomized control trial with double blinding. We utilized statistical modeling with TF-IDF.")
    
    pdf.cell(200, 10, txt="RESULTS", ln=1)
    pdf.multi_cell(0, 10, txt="The analysis shows a 25% improvement over baseline metrics. P-values sit strictly under 0.05, establishing strong significance.")
    
    pdf.cell(200, 10, txt="DISCUSSION", ln=1)
    pdf.multi_cell(0, 10, txt="While finding significant results, this study is limited by the small sample size and temporal constraints. Future work should investigate larger populations.")
    
    pdf.output(filename)

make_pdf('sample_1.pdf', 'Deep Insights into Machine Learning')
make_pdf('sample_2.pdf', 'Understanding AI Methodologies')
