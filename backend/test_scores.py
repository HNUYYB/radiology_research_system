import math, re

papers = [
    {'title': 'Deep Learning for Acute Stroke Detection on Non-Contrast CT', 'abstract': 'Purpose: develop deep learning model acute stroke detection non-contrast CT scans. Trained convolutional neural network 500 CT scans stroke patients. Model achieved 95 percent sensitivity.', 'journal': 'Radiology', 'pubdate': '2024'},
    {'title': 'Machine Learning in Neuroimaging A Review', 'abstract': 'Review summarizes machine learning neuroimaging. Discuss deep learning support vector machines brain image analysis.', 'journal': 'NeuroImage', 'pubdate': '2023'},
    {'title': 'AI Assisted Diagnosis Pulmonary Nodules Chest CT', 'abstract': 'Deep learning system detecting pulmonary nodules chest CT. Trained 1000 cases validated 200 cases.', 'journal': 'European Radiology', 'pubdate': '2025'},
    {'title': 'Stroke Imaging Current Status Future Directions', 'abstract': 'Reviews imaging techniques stroke diagnosis CT MRI CT perfusion. Discusses advanced imaging acute stroke management.', 'journal': 'Stroke', 'pubdate': '2022'},
]

# Scenario 1: Chinese-only query (old way - fails to match English)
query_cn = '基于深度学习的脑卒中CT辅助诊断'
query_words_cn = [w for w in query_cn.lower().split() if len(w) > 1 and bool(re.match(r'^[a-zA-Z0-9_\-]+$', w))]
print('=== Scenario 1: Chinese-only query (OLD) ===')
print(f'Query: {query_cn}')
print(f'English keywords found: {query_words_cn}')
print()

# Scenario 2: English keywords extracted (new way)
query_en = 'CT stroke deep learning diagnosis 基于深度学习的脑卒中CT辅助诊断'
query_words_en = [w for w in query_en.lower().split() if len(w) > 1 and bool(re.match(r'^[a-zA-Z0-9_\-]+$', w))]
print('=== Scenario 2: English keywords + Chinese query (NEW) ===')
print(f'Query: {query_en}')
print(f'English keywords found: {query_words_en}')
print()

for idx, p in enumerate(papers):
    score = 0.0
    title = p['title'].lower()
    abstract = p['abstract'].lower()

    # Title match max 35
    tm = sum(1 for w in query_words_en if w in title)
    if tm > 0:
        coverage = tm / len(query_words_en)
        score += coverage * 35.0
        for i in range(len(query_words_en)-1):
            bigram = f'{query_words_en[i]} {query_words_en[i+1]}'
            if bigram in title:
                score += 5.0

    # Abstract match max 30
    am = sum(1 for w in query_words_en if w in abstract)
    if am > 0:
        coverage = am / len(query_words_en)
        score += coverage * 20.0
        tc = sum(abstract.count(w) for w in query_words_en if w in abstract)
        score += min(math.log(1+tc)*2, 10)

    # Recency max 12
    year = int(p['pubdate'])
    diff = 2026 - year
    recency = 100 * math.exp(-0.15 * max(diff, 0))
    score += recency * 0.12

    # Journal max 8
    j = p['journal'].lower()
    if 'radiology' in j or 'european' in j:
        score += 7.0
    elif 'neuroimage' in j:
        score += 7.5
    else:
        score += 3.0

    algo = min(score, 100.0)

    llm_raw = [3, 2, 1, 2][idx]
    llm = (llm_raw / 3.0) * 100.0

    algo_signal = algo > 10
    fused = (algo * 0.3 + llm * 0.7) if algo_signal else llm
    status = 'PASS' if fused >= 25 else 'FAIL'

    print(f'Paper {idx+1}: algo={algo:.1f} | llm={llm:.1f} | fused={fused:.1f} [{status}]')
    print(f'  {p["title"][:70]}')
    print()
