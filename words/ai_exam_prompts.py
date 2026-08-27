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


def cet6_translation_help_prompt(question, paragraph, user_level_desc):
    """六级段落翻译（汉译英）解析提示词：分析中文段落，给出词汇、句式与参考译文"""
    return f"""你是一位大学英语六级翻译辅导老师。请帮助用户将以下中文段落翻译成英文。

【用户的词汇水平画像】
{user_level_desc}

【中文段落】
{paragraph}

请从以下四个层面帮助用户（用中文回答，Markdown 格式）：
## 1. 关键词与表达
列出段落中相对难翻译或值得记的中文词组/短语，给出对应的英文译法（优先使用落在用户当前词汇量内的词），并标注是否超纲。

## 2. 句式拆解与建议
按意群把中文段落拆成 4-6 个小句，逐句说明：
- 中文原句
- 推荐的英文句式（主谓宾 / 倒装 / 强调句 / 从句 / 分词作状语等）
- 翻译时需注意的语序调整、时态、单复数、冠词等

## 3. 参考译文
给出一份通顺、贴合用户词汇水平的完整英文参考译文（约 150-200 词）。

## 4. 翻译技巧点拨
总结汉译英这类段落翻译的 2-3 条通用技巧（如：化整为零拆短句、被动转主动、并列句合并、删冗余修饰等）。

【真题背景】
大学英语六级 {question.year}年段落翻译真题
{question.title}"""


def cet6_translation_grading_prompt(question, user_translation, reference=None):
    """批改用户英文译文（汉译英），结构化 JSON 输出"""
    ref_part = f'\n【参考译文】\n{reference}' if reference else ''
    return f"""你是一位大学英语六级翻译阅卷老师。请对用户的英文译文进行批改，并以严格的 JSON 对象格式输出（不要输出任何其他文字）。

【批改维度】（每项 0-10 分）
1. accuracy：忠实度（是否准确传达原文意思，有无漏译、误译）
2. grammar：语法（时态、单复数、冠词、从句结构是否正确）
3. vocabulary：用词（词汇是否恰当、是否回避了重复、有无中式英语）
4. fluency：通顺度（英文表达是否自然、地道）
5. coherence：连贯度（句间衔接、上下文逻辑是否清晰）

【输出格式】
{{
  "scores": {{"accuracy": 8, "grammar": 7, "vocabulary": 8, "fluency": 7, "coherence": 8}},
  "total": 38,
  "comments": "总评：一段话整体点评（中文）",
  "errors": [{{"original": "用户译句", "corrected": "改进后", "reason": "原因（中文）"}}],
  "suggestions": ["改进建议1（中文）", "改进建议2", "改进建议3"],
  "model_translation": "更佳的参考英文译文"
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


def personal_template_prompt(user_level_desc, practice_summary):
    """基于用户词汇画像 + 历史练习记录，生成专属作文模板的提示词"""
    return f"""你是一位资深的考研英语写作教师，擅长为每个学生量身定制作文模板。请根据用户的词汇水平和历史练习情况，生成一份【专属作文模板】，让用户能直接套用。

【用户的词汇水平画像】
{user_level_desc}

【用户的历史练习情况】
{practice_summary}

【输出要求——Markdown 排版规范，务必严格遵守】

1. 标题层级：
   - 全文只有一个 "# 你的专属考研英语写作模板"（一级标题）
   - 五个大板块使用 "## 一、我的常用高分句型" 格式（二级标题，必须带编号"一、二、三、四、五、"）
   - 板块内子项用 "### 句型 1：开头引入——图画/图表描述" 或 "#### 开头句（3个）" 格式（三/四级标题）
   - 禁止用空格 + 文字充当标题，必须用 # 号

2. 列表与项目：
   - 多个并列项目一律用有序列表（1. 2. 3.）或无序列表（- ）
   - 禁止用"句型 1：XXX  句型 2：XXX"这样的扁平文字罗列
   - 子项如果有分类，用嵌套列表或四级标题分组

3. 表格：
   - 「我的词汇升级卡」板块 MUST 使用标准 Markdown 表格，格式如下：
     | 原表达 | 升级为 | 例句 |
     |---|---|---|
     | use（使用） | adopt（采用） | We should adopt a new method. |
   - 分隔行（|---|---|---|）绝对不能省！否则无法正确渲染

4. 英文模板句展示：
   - 单独的英文模板句用引用块 "> 英文句子" 包裹（> 开头）
   - 英文例句前面加 "　例句：" 引导，英文部分用 *斜体* 包裹

5. 加粗标注：
   - 高级词汇、高分亮点、重点提示用 **加粗** 标注
   - 易错点、注意事项用 **注意：** 开头强调
   - 记忆口诀、要点提示用 "　　"（两个全角空格）缩进开头

6. 分段与空行：
   - 每个段落之间空一行，段首不要缩进
   - 列表项、引用块、表格之间务必留空行，避免粘连

【内容结构（五个板块，严格按下列框架输出）】

## 一、我的常用高分句型
> 基于你已掌握的词汇设计，全部经过批改验证，可直接套用。

### 句型 1：开头引入——图画/图表描述
**中文示意：** 如图所示，我们可以清楚地看到⋯⋯
英文模板：
> As is **vividly** shown in the picture, we can see clearly that ______.

　用 `As is shown` 开头比 `The picture shows` 更正式。
　例句：*As is vividly shown in the picture, a young man is addicted to his phone.*

### 句型 2：...（3-5 个，依次类推）

---

## 二、我的万能开头 / 衔接 / 结尾

#### 开头句（3个）
1. **As is vividly shown in the picture, ______.**
   　例：*As is vividly shown in the picture, a senior man is teaching a child to write.*
2. ...

#### 过渡衔接句（3个）
1. **In addition, ______.**
2. ...

#### 结尾升华句（3个）
1. **In a word, it is **high time** that we took **effective** actions.**
   　**注意：** `It is high time that` 后从句用过去时（虚拟语气），考研高频考点！
2. ...

---

## 三、我的常犯错误清单
> 根据你的历史批改记录整理，这些是你最容易丢分的地方，务必牢记！

### 错误 1：`like` 与 `such as` 混用
　错误：*Sketch patterns like blossoms on its surface.*
　正确：*Sketch patterns such as blossoms on its surface.*
　记忆口诀：书面语用 `such as`，口语才用 `like`。

### 错误 2：...（3-5 个）

---

## 四、我的词汇升级卡
> 每次写作前扫一眼，挑 2-3 个用进去，慢慢变成你自己的。

| 原表达（你已经会的） | 高级表达（加粗学习） | 例句（用你已掌握的词汇造句） |
|---|---|---|
| **use**（使用） | **adopt**（采用） | We should **adopt** a new method to solve this problem. |
| ...（5-8 行） | ... | ... |

---

## 五、我的写作流程建议
> 根据你的得分情况与薄弱环节，给你 4 条最实用的提分建议。

### 建议 1：先搭骨架，再填肉——5 分钟列提纲
拿到题目后，不要直接动笔。花 5 分钟在草稿纸上写下：
　开头（描述图画/图表/书信目的）→ 用模板句型 1 或书信开头
　中间（分析原因/举例）→ 用模板句型 3 或 4
　结尾（总结/建议）→ 用模板句型 5 + 结尾升华句

### 建议 2：...（3-4 条）

【其他硬性要求】
- 所有英文表达主体必须落在用户已掌握词汇范围内，只适量引入 1-2 个更高阶表达并标注 **加粗**
- 语气亲切、可操作，让用户真正能背下来、用得上
- 绝对不要输出 Markdown 代码块包裹（不要 ```markdown ... ```），直接输出纯 Markdown 文本
- 全文不要出现"下面的模板""以上建议"等指代语，保持独立成章"""