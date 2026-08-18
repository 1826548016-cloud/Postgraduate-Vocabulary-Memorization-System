"""考研写作工坊 - AI 提示词与词汇画像构建"""


def build_vocabulary_profile(max_words=80):
    """根据学习进度构建用户词汇画像（供 AI 生成作文时参考）。
    返回结构化字符串描述用户已掌握词汇水平。"""
    from .models import StudyProgress, Word

    mastered = StudyProgress.objects.filter(
        status='mastered', is_excluded=False
    ).select_related('word')[:max_words]

    words = [
        {'word': p.word.word, 'category': p.word.category, 'level': p.mastery_level}
        for p in mastered
    ]

    total = StudyProgress.objects.filter(status='mastered', is_excluded=False).count()
    total_in_db = Word.objects.count()

    # 统计词频分布
    from collections import Counter
    cat_counter = Counter(w['category'] for w in words)

    parts = [
        f'用户当前已掌握单词总数：约 {total} 个（词库总量 {total_in_db}）。',
    ]
    if cat_counter:
        desc = '、'.join(f'{name}词 {n} 个' for name, n in cat_counter.most_common())
        parts.append(f'掌握词汇类别分布：{desc}。')
    if words:
        sample = '、'.join(w['word'] for w in words[:60])
        parts.append(f'已掌握词汇取样（仅作参考，不代表全部）：{sample}。')
    parts.append(
        '注意：AI 生成的作文中，主体词汇必须控制在用户已掌握范围内，'
        '只可适量引入少量（3-6 个）略高于用户水平的高级表达并加粗标注，供用户学习。'
    )
    return '\n'.join(parts)


def essay_generation_prompt(question, user_level_desc, style='standard'):
    """生成作文的提示词。style: standard / easy / advanced"""
    if style == 'easy':
        level_hint = '使用更简单、更基础的词汇和句式，确保用户能轻松读懂。'
    elif style == 'advanced':
        level_hint = '使用较为高级的词汇和复杂句式（考研高分水平），供用户学习模仿。'
    else:
        level_hint = '使用用户当前已掌握的词汇为主体，适当引入少量高级表达。'

    return f"""你是一位专业的考研英语写作指导教师。请根据以下真题要求，为用户写一篇范文。

【用户的词汇水平画像】
{user_level_desc}

【作文要求】
{level_hint}
- 小作文控制在 100 词左右，大作文控制在 160-200 词。
- 结构完整，符合该体裁的格式规范（书信、通知等格式要正确）。
- 语言自然地道，避免中式英语。
- 如需引入高级表达，请用【】括号标出这些新词/新表达，方便用户学习。

【真题信息】
考试：{question.get_exam_type_display()}（{question.year}年）
题型：{question.get_question_type_display()} {('- ' + question.genre) if question.genre else ''}
题目：{question.title}
题目内容：{question.content}
写作要求：{question.prompt or '（无额外要求）'}

请直接输出范文正文，不要多余解释。"""


def essay_grading_prompt(question, user_essay):
    """批改用户作文的提示词，要求结构化 JSON 输出"""
    return f"""你是一位经验丰富的考研英语阅卷老师。请对以下学生作文进行批改，并以严格的 JSON 对象格式输出（不要输出任何其他文字）。

【批改维度】（每项 0-10 分）
1. vocabulary：词汇准确性与丰富度
2. grammar：语法正确性
3. coherence：篇章连贯性
4. relevance：切题度
5. richness：语言表现力

【输出格式】
{{
  "scores": {{"vocabulary": 8, "grammar": 7, "coherence": 8, "relevance": 9, "richness": 6}},
  "total": 38,
  "comments": "总评：一段话整体点评（中文）",
  "errors": [{{"original": "原句", "corrected": "修改后", "reason": "错误原因（中文）"}}],
  "suggestions": ["改进建议1（中文）", "改进建议2", "改进建议3"],
  "advanced_expressions": [{{"original": "简单表达", "advanced": "高级同义替换", "explain": "用法说明（中文）"}}],
  "model_essay": "修改后的完整范文（贴合学生水平、小幅拔高）"
}}

【真题信息】
考试：{question.get_exam_type_display()}（{question.year}年）
题型：{question.get_question_type_display()} {('- ' + question.genre) if question.genre else ''}
题目：{question.title}
题目内容：{question.content}

【学生作文】
{user_essay}"""


def translation_help_prompt(question, sentence, user_level_desc):
    """翻译真题句子解析提示词"""
    return f"""你是一位考研英语翻译辅导老师。请帮助用户解析并翻译以下英文句子。

【用户的词汇水平画像】
{user_level_desc}

【句子】
{sentence}

请从以下三个层面帮助用户（用中文回答，Markdown 格式）：
## 1. 语法结构拆解
把句子按意群拆开，标出主干、从句、修饰成分，说明各部分的逻辑关系。

## 2. 词汇点拨
标出句子中相对难或值得记的词汇/短语，给出释义和在此处的用法。可标注哪些词超出用户当前词汇量。

## 3. 参考译文 + 翻译技巧
给出通顺的参考译文，并说明翻译这类句式时需要注意的技巧（如长句拆分、语序调整、增词减词等）。

【真题背景】
{question.get_exam_type_display()} {question.year}年翻译真题
{question.title}"""


def translation_grading_prompt(question, user_translation, reference=None):
    """批改用户译文提示词，结构化 JSON 输出"""
    ref_part = f'\n【官方/参考译文】\n{reference}' if reference else ''
    return f"""你是一位考研英语翻译阅卷老师。请对用户的译文进行批改，并以严格的 JSON 对象格式输出（不要输出任何其他文字）。

【批改维度】（每项 0-10 分）
1. accuracy：忠实度（是否准确传达原意）
2. fluency：通顺度（中文表达是否自然）
3. completeness：完整度（是否漏译）

【输出格式】
{{
  "scores": {{"accuracy": 8, "fluency": 7, "completeness": 9}},
  "total": 24,
  "comments": "总评：一段话整体点评（中文）",
  "errors": [{{"original": "用户译句", "corrected": "改进后", "reason": "原因（中文）"}}],
  "suggestions": ["改进建议1（中文）", "改进建议2", "改进建议3"],
  "model_translation": "更佳的参考译文"
}}
{ref_part}
【用户译文】
{user_translation}"""


def themes_report_prompt(questions_text):
    """历年真题主题规律分析提示词"""
    return f"""你是一位研究考研英语命题规律多年的专家。以下是部分历年真题，请分析：

1. 高频主题归纳（按出现频次排序）
2. 常见题型分析（书信各类型、通知、图画、图表等）
3. 每种题型的高分写作要点（条数结构、常用句式）
4. 对备考的建议（词汇、模板、审题技巧）

用中文回答，Markdown 格式输出。

【真题数据】
{questions_text}"""