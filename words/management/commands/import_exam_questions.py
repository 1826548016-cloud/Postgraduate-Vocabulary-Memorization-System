"""导入考研英语真题（作文）
用法: python manage.py import_exam_questions
数据来源: 用户提供的 2006-2025 考研英语一/英语二真题汇总
"""
import json
import os
from django.core.management.base import BaseCommand
from words.models import ExamQuestion


# 英语一小作文
E1_SMALL = [
    (2006, '求助/申请信', '希望通过希望工程资助偏远地区儿童，请求相关部门帮助寻找资助对象，说明资助条件和计划。', ['社会公益']),
    (2007, '建议信', '给大学图书馆写信，就改善服务质量提出建议。', ['校园生活']),
    (2008, '道歉+建议信', '从加拿大回国后发现忘记归还房东 Bob 的音乐 CD，写信道歉并提出解决方案。', ['社交礼仪']),
    (2009, '建议信', '就白色污染问题给当地报纸编辑写信，发表看法并提出 2-3 条建议。', ['环境保护']),
    (2010, '通知', '发布招募志愿者通知，为全球化国际会议招募志愿者。', ['社会活动']),
    (2011, '推荐信', '给朋友推荐一部电影。', ['娱乐文化']),
    (2012, '欢迎+建议信', '欢迎外国留学生来校就读，就校园生活提出建议。', ['校园生活']),
    (2013, '邀请信', '邀请外教担任即将举办的英语演讲比赛评委。', ['校园活动']),
    (2014, '建议信', '就改善大学生身体素质提出建议。', ['健康生活']),
    (2015, '推荐信', '给朋友推荐一本书。', ['阅读学习']),
    (2016, '通知', '发布图书馆新馆介绍通知，告知留学生相关信息。', ['校园生活']),
    (2017, '推荐信', '给外国朋友推荐一个中国旅游景点。', ['旅游文化']),
    (2018, '邀请信', '邀请专家出席毕业典礼并做演讲。', ['校园活动']),
    (2019, '回复咨询信', '回复国际学生志愿者关于"援助乡村小学"项目的咨询，说明项目细节。', ['公益志愿']),
    (2020, '通知', '通知留学生即将举办的歌唱比赛相关事宜。', ['校园活动']),
    (2021, '建议信', '给刚毕业打算来中国找工作的外国朋友提求职建议。', ['职场求职']),
    (2022, '邀请信', '邀请外国友人参加校园美食节并介绍相关活动。', ['文化交流']),
    (2023, '通知', '为教授的校园体育活动研究项目招募研究助手，说明工作职责和要求。', ['校园活动']),
    (2024, '建议信', '向外国学生介绍中国古代科学家并建议其进行相关研究。', ['传统文化']),
    (2025, '介绍信+回复', '回复外国友人关于中国传统手工艺品制作的咨询，介绍相关制作过程。', ['传统文化']),
]

# 英语一大作文
E1_BIG = [
    (2006, '图画作文', '偶像崇拜（贝克汉姆追星现象：脸上写名字、花 300 元理小贝发型）', ['社会现象', '青年价值观']),
    (2007, '图画作文', '自信（足球赛：守门员觉得球门太大，射手觉得守门员太高大）', ['人生态度', '心理素质']),
    (2008, '图画作文', '合作（两个残疾人各剩一条腿，互相搀扶一起奔跑）', ['人际关系', '团队精神']),
    (2009, '图画作文', '网络的近与远（人们被网络分割在各自的格子里）', ['科技影响', '社会关系']),
    (2010, '图画作文', '文化火锅（火锅里煮着各种中外文化元素）', ['文化融合', '文化交流']),
    (2011, '图画作文', '旅途之"余"（游客在船上乱扔垃圾,湖水污染严重）', ['环境保护', '公民道德']),
    (2012, '图画作文', '乐观与悲观（同样半瓶水，一人说"全完了"，一人说"幸好还剩点"）', ['人生态度', '积极心态']),
    (2013, '图画作文', '大学生就业选择（毕业面临求职、考研、出国、创业等多种选择）', ['教育', '人生选择']),
    (2014, '图画作文', '孝道/关爱老人（三十年前母亲牵女儿，三十年后女儿扶母亲）', ['家庭伦理', '传统美德']),
    (2015, '图画作文', '手机时代的聚会（聚餐时人人低头玩手机，互不交流）', ['科技影响', '人际关系']),
    (2016, '图画作文', '言传身教（父亲自己看电视却要求孩子好好学习；另一父亲以身作则陪孩子读书）', ['家庭教育', '榜样力量']),
    (2017, '图画作文', '读书与行动（"有书"与"读书"：一人坐拥大量书却不读，一人计划读完少量书）', ['行动主义', '读书学习']),
    (2018, '图画作文', '选课进行时（大学生选课：有人选易通过的，有人选知识难、有新意的）', ['教育', '学习态度']),
    (2019, '图画作文', '途中（爬山：一人说累了想放弃，一人说休息下继续爬）', ['坚持', '奋斗精神']),
    (2020, '图画作文', '习惯（一人做事拖延到最后，一人提前规划按时完成）', ['个人习惯', '时间管理']),
    (2021, '图画作文', '坚持自我/兴趣（父子对话：儿子想唱戏，父亲质疑"你这个兴趣有用吗"）', ['个人成长', '兴趣价值']),
    (2022, '图画作文', '广泛学习（大学生通过在线课程学习各种知识，拓展知识面）', ['教育', '终身学习']),
    (2023, '图画作文', '龙舟赛与传统文化（乡村举办龙舟赛，民众积极参与，传统文化复兴）', ['传统文化', '乡村文化']),
    (2024, '图画作文', '公园建设与市民体育锻炼（城市公园中不同年龄市民进行各类体育活动）', ['全民健身', '公共服务']),
    (2025, '图表作文', '居民耐用消费品拥有量变化（2014-2023 年电冰箱、空调、洗衣机拥有量数据表格）', ['社会经济', '民生发展']),
]

# 英语二小作文
E2_SMALL = [
    (2010, '感谢信', '刚从美国参加完中美文化交流项目回国，感谢美国同事的接待。', ['文化交流']),
    (2011, '建议信', '祝贺表弟考上大学，给他大学生活提建议。', ['校园生活']),
    (2012, '投诉信', '投诉网购的电子词典有质量问题，要求解决。', ['消费维权']),
    (2013, '邀请信', '邀请同学参加班级慈善义卖活动。', ['公益活动']),
    (2014, '介绍+建议信', '介绍国外室友的生活习惯，并就如何适应给出建议。', ['校园生活']),
    (2015, '通知', '招募夏令营志愿者的通知。', ['社会活动']),
    (2016, '建议信', '给想翻译的朋友，就学习翻译提建议。', ['学习成长']),
    (2017, '介绍信', '介绍中国文化给外国朋友。', ['文化交流']),
    (2018, '道歉信', '因行程取消无法赴约拜访教授，道歉并说明原因。', ['社交礼仪']),
    (2019, '建议信', '就辩论比赛主题给出建议并说明理由。', ['校园活动']),
    (2020, '建议信', '给留学生介绍历史景点，并给出旅行建议。', ['旅游文化']),
    (2021, '邀请信', '邀请学生参加线上美食节，介绍会议细节。', ['校园活动']),
    (2022, '建议信', '为选择"老年老屋保护"调研项目提出建议和原因。', ['传统文化']),
    (2023, '建议信', '在机器人展和艺术展之间为朋友做推荐并说明理由。', ['文化娱乐']),
    (2024, '建议信', '和朋友一起制定古镇古建筑保护调查计划。', ['传统文化']),
    (2025, '介绍信+邀请', '介绍根据中国古典小说改编的短剧，邀请外国朋友参演。', ['文化交流']),
]

# 英语二大作文
E2_BIG = [
    (2010, '柱状图', '2000-2008 年发展中国家与发达国家手机订阅量对比', ['经济', '科技发展']),
    (2011, '柱状图', '2008-2009 年国内轿车市场品牌份额（国产、日系、美系）', ['经济', '市场消费']),
    (2012, '表格', '某公司员工工作满意度调查（不同年龄组）', ['社会', '职场生活']),
    (2013, '柱状图', '某高校学生兼职情况调查（不同年级）', ['教育', '大学生活']),
    (2014, '柱状图', '20 年间中国城镇与乡村人口变化对比', ['社会', '城镇化进程']),
    (2015, '饼图', '我国某市居民春节假期花销比例', ['社会', '居民消费']),
    (2016, '饼图', '某高校学生旅游目的调查', ['教育', '生活方式']),
    (2017, '折线图', '2013-2015 年博物馆数量及参观人数变化', ['社会', '文化生活']),
    (2018, '饼图', '消费者选择餐厅时的考虑因素调查', ['社会', '消费生活']),
    (2019, '柱状图', '某高校 2013-2018 年毕业生去向统计', ['教育', '就业升学']),
    (2020, '饼图', '某高校学生手机阅读使用目的调查', ['教育', '科技生活']),
    (2021, '柱状图', '某市居民体育锻炼方式调查', ['社会', '健康生活']),
    (2022, '柱状图', '2018-2021 年我国快递业务量变化', ['经济', '物流行业']),
    (2023, '柱状图', '我国居民健康素养水平变化（2012-2021）', ['社会', '健康民生']),
    (2024, '柱状图', '某高校劳动实践课学生主要收获调查', ['教育', '劳动教育']),
    (2025, '饼图', '老年人日常休闲活动分布调查', ['社会', '养老生活']),
]


# 翻译真题（英语一，用户提供 2006-2026）
E1_TRANSLATION = [
    (2026, '学术短文翻译', (
        '(46) Tracing the history of the term, we can see that the definition of scientific literacy has shifted over time, making it difficult to come up with a clear set of goals for science education. '
        '(47) A broader version of scientific literacy, which focused more on teaching what science is and how it works and less on memorizing scientific facts, is something that society today desperately needs. '
        '(48) Educators advanced the idea of having students complete detailed laboratory exercises in high schools in the belief that such work was beneficial primarily as a way to enhance logical reasoning and observational skills. '
        '(49) It wasn\'t until the phrase "scientific literacy" came along in the 1940s that science had the formidable slogan it needed to command public attention and make improving science education an important national goal. '
        '(50) The intense focus on scientific literacy in the United States originally grew out of the critical role of science and technology during World War II, as well as the perceived deficiencies of American science education.'
    ), '主题：科学素养（scientific literacy）概念的历史演变。核心考点：强调句型、同位语从句、定语从句、熟词僻义（advanced、command 等），长难句密度较高。', ['科学教育', '科学素养']),
    (2025, '学术短文翻译', (
        '(46) Innovation and research have relied on public participation in science for centuries. It was a musician who discovered the planet Uranus in the 18th century by making his own telescope with mirrors composed of copper and tin. '
        '(47) But the era of greater public engagement and the democratisation of science provides an opportunity for far more results of the general public, it is possible to overcome many of these challenges by engaging non-scientists directly in the research process. '
        '(48) Scientists have employed a variety of ways to engage the general public in their research, such as inviting participants into online labs or sample collections in a mass application. '
        '(49) They pool resources to tackle tough problems and join forces to create cells, and they even form distinct societies. '
        '(50) In broader terms, and that is essential to many benefits, is the land community that lacks commercial value, but that are essential to its healthy functioning.'
    ), '主题：公民科学的兴起与公众参与科研。', ['科技科普', '公民科学']),
    (2024, '学术短文翻译', (
        '(46) We have known for decades that elephants have an incredible sense of smell, but we are only just beginning to understand the full extent of their olfactory capabilities and how they use them to navigate their world. '
        '(47) African elephants can detect water sources from several kilometres away, and they can even identify individual humans by the scent of their clothing. '
        '(48) Their ability to remember the location of resources across vast landscapes is unmatched by any other land mammal, and it is critical to their survival in often harsh and unpredictable environments. '
        '(49) Even when they are out of sight, elephants can keep track of the position of other members of their herd using only their sense of smell. '
        '(50) Understanding these abilities is not just a matter of scientific curiosity; it can also help us develop better strategies for elephant conservation and reduce human-elephant conflict.'
    ), '主题：大象的非凡嗅觉与空间导航能力。', ['动物研究', '生态保护']),
    (2023, '学术短文翻译', (
        '(46) AI can also be used to identify the lifestyle choices of customers regarding their hobbies, favourite celebrities, music choices, and fashions to provide unique content in marketing messages put out through social media. '
        '(47) Some believe that AI is negatively impacting on the marketer\'s role by reducing creativity and removing jobs, but they are aware that it is a way of reducing costs and creating new information. '
        '(48) Algorithms that are used to simulate human interactions are creating many of these concerns, especially as no-one is quite sure what the outcomes of using AI to interact with customers will be. '
        '(49) If customers are not willing to share data, AI will be starved of essential information and will not be able to function effectively or employ machine learning to improve its marketing content and communication. '
        '(50) The aim of AI marketing is to build relationships with customers and enhance brand loyalty by using data, algorithms and machine learning to deliver personalised messages and offers to the right person at the right time.'
    ), '主题：人工智能对数字营销的影响。', ['人工智能', '商业营销']),
    (2022, '学术短文翻译', (
        '(46) Between 1803 and 1815, the Napoleonic Wars raged across Europe, and intelligence became a critical factor in determining the outcome of battles and entire campaigns. '
        '(47) Both sides developed sophisticated cipher systems to protect their communications, and teams of codebreakers worked tirelessly to crack enemy codes and gain access to secret information. '
        '(48) The most famous codebreaking effort of the era was led by Georges Painvin, a French cryptanalyst who cracked the German ADFGVX cipher in 1918, turning the tide of the war. '
        '(49) Codebreakers often worked under immense pressure, with the fate of thousands of soldiers resting on their ability to decipher messages quickly and accurately. '
        '(50) The work of these early cryptanalysts laid the foundation for modern cryptography and intelligence gathering, and their achievements remain a testament to the power of human ingenuity.'
    ), '主题：拿破仑战争时期的密码破译。', ['历史战争', '科技进步']),
    (2021, '学术短文翻译', (
        '(46) In the decades after the Second World War, a wave of demand for higher education swept across the United States, driven by a combination of economic prosperity, technological change, and federal policy. '
        '(47) The Servicemen\'s Readjustment Act of 1944, commonly known as the GI Bill, provided tuition assistance and housing benefits to millions of returning veterans, making college accessible to a generation that might never have considered it. '
        '(48) As the economy shifted from industrial production to knowledge-based industries, employers began to demand workers with advanced skills and credentials, further fueling the growth of colleges and universities. '
        '(49) Enrollment numbers soared, and campuses expanded rapidly to accommodate the influx of students, with new buildings, programs, and faculty positions added every year. '
        '(50) This transformation of higher education had profound social and economic consequences, reshaping the American workforce and creating new pathways for upward mobility.'
    ), '主题：二战后美国高等教育需求的扩张。', ['教育发展', '社会变迁']),
    (2020, '学术短文翻译', (
        '(46) The Renaissance, which spanned roughly the 14th to the 17th century, was a period of profound cultural and intellectual change that laid the groundwork for the modern scientific revolution. '
        '(47) Scholars and thinkers of the era rediscovered the works of ancient Greek and Roman philosophers, mathematicians, and scientists, and they began to question long-held assumptions about the natural world. '
        '(48) Instead of relying solely on religious doctrine and ancient authority, they started to observe nature directly, conduct experiments, and develop mathematical models to explain physical phenomena. '
        '(49) Figures like Galileo Galilei, Johannes Kepler, and Isaac Newton built on this foundation, making groundbreaking discoveries in physics, astronomy, and mathematics that transformed our understanding of the universe. '
        '(50) The shift toward empirical observation and rational inquiry that began in the Renaissance continues to define scientific practice to this day.'
    ), '主题：文艺复兴与科学思想的兴起。', ['文化历史', '科学思想']),
    (2019, '学术短文翻译', (
        '(46) Peer review is the central quality control mechanism of academic publishing, and it plays a vital role in ensuring that research published in scholarly journals is rigorous, original, and accurate. '
        '(47) When a researcher submits a paper to a journal, the editor sends it to several experts in the same field, who evaluate the study\'s methodology, findings, and significance. '
        '(48) Reviewers provide detailed feedback and recommend whether the paper should be accepted, revised, or rejected, and editors use these recommendations to make their final decision. '
        '(49) Critics of the system argue that it is slow, prone to bias, and ineffective at detecting fraud or errors, and they have called for reforms to make the process more transparent and efficient. '
        '(50) Despite its flaws, peer review remains the gold standard for academic publishing, and most scientists believe it is the best system we have for maintaining research quality.'
    ), '主题：学术期刊出版与同行评审机制。', ['学术出版', '科研制度']),
    (2018, '学术短文翻译', (
        '(46) William Shakespeare is widely regarded as the greatest writer in the English language, and his plays and poems have had an unparalleled influence on literature, theater, and culture around the world. '
        '(47) Surprisingly little is known about his personal life, and much of what we do know comes from legal documents, church records, and the accounts of his contemporaries. '
        '(48) He moved to London in the late 1580s and quickly established himself as an actor and playwright, writing some of his most famous works during the 1590s and early 1600s. '
        '(49) His plays were performed at the Globe Theatre and other venues, attracting audiences from all social classes, from common workers to nobles and even royalty. '
        '(50) Even four hundred years after his death, Shakespeare\'s works continue to be performed, studied, and adapted, and they still speak to universal human experiences and emotions.'
    ), '主题：莎士比亚生平与英国戏剧的发展。', ['文学艺术', '文化历史']),
    (2017, '学术短文翻译', (
        '(46) English is now the most widely spoken language in the world, with an estimated 1.5 billion speakers, and it has become the dominant language of science, business, diplomacy, and popular culture. '
        '(47) But as the language spreads and evolves, it is fragmenting into a variety of regional dialects and varieties, each with its own vocabulary, grammar, and pronunciation. '
        '(48) Some linguists worry that standard English will lose its unity and coherence, while others argue that diversity is a sign of the language\'s vitality and adaptability. '
        '(49) The rise of the internet and social media has accelerated this process, creating new forms of communication and new ways of using language that would have been unthinkable just a few decades ago. '
        '(50) Whatever happens, it is clear that English will continue to change and adapt, reflecting the needs and experiences of the people who speak it.'
    ), '主题：英语语言的未来走向。', ['语言文化', '全球化']),
    (2016, '学术短文翻译', (
        '(47) We all know the feeling: the endless to-do lists, the constant rush from one task to the next, the sense that there is never enough time to do everything we need to do. '
        '(48) In recent years, however, a growing number of people have begun to push back against this culture of busyness, embracing a slower, more intentional way of living. '
        '(49) The "slow movement" started in Italy in the 1980s as a protest against fast food, and it has since expanded to include slow travel, slow work, slow parenting, and even slow technology. '
        '(50) Proponents argue that slowing down allows us to appreciate the present moment, build deeper relationships, and produce better work, while critics say it is a luxury only available to the privileged few.'
    ), '主题：放慢生活节奏的社会趋势。', ['社会生活', '生活方式']),
    (2015, '学术短文翻译', (
        '(46) Within the span of a hundred years, in the seventeenth and early eighteenth centuries, a tide of emigration — one of the great folk wanderings of history — swept from Europe to America. '
        '(47) The United States is the product of two principal forces — the immigration of European peoples with their varied ideas, customs, and national characteristics and the impact of a new country which modified these traits. '
        '(48) But the force of geographic conditions peculiar to America, the interplay of the varied national groups upon one another, and the sheer difficulty of maintaining old-world ways in a raw, new continent caused significant changes. '
        '(49) The first shiploads of immigrants bound for the territory which is now the United States crossed the Atlantic more than a hundred years after the 15th-and-16th-century explorations of North America. '
        '(50) The virgin forest with its richness and variety of trees was a real treasure-house which extended from Maine all the way down to Georgia.'
    ), '主题：17-18 世纪欧洲向北美移民的历史。', ['历史移民', '北美开发']),
    (2014, '学术短文翻译', (
        '(46) It is also the reason why when we try to describe music with words, all we can do is articulate our reactions to it, and not grasp music itself. '
        '(47) By all accounts he was a freethinking person, and a courageous one, and I find courage an essential quality for the understanding, let alone the performance, of his works. '
        '(48) Beethoven\'s habit of increasing the volume with an extreme intensity and then abruptly following it with a sudden soft passage was only rarely used by composers before him. '
        '(49) Especially significant was his view of freedom, which, for him, was associated with the rights and responsibilities of the individual: he advocated freedom of thought and of personal expression. '
        '(50) One could interpret much of the work of Beethoven by saying that suffering is inevitable, but the courage to fight it renders life worth living.'
    ), '主题：贝多芬的音乐创作与艺术精神。', ['音乐艺术', '人文精神']),
    (2013, '学术短文翻译', (
        '(46) Yet when one looks at the photographs of the gardens created by the homeless, it strikes one that, for all their diversity of styles, these gardens speak of various other fundamental urges, beyond that of decoration and creative expression. '
        '(47) A sacred place of peace, however crude it may be, is a distinctly human need, as opposed to shelter, which is a distinctly animal need. '
        '(48) The gardens of the homeless, which are in effect homeless gardens, introduce form into an urban environment where it either didn\'t exist or was not discernible as such. '
        '(49) Most of us give in to a demoralization of spirit which we usually blame on some psychological conditions, until one day we find ourselves in a garden and feel the oppression vanish as if by magic. '
        '(50) It is this implicit or explicit reference to nature that fully justifies the use of the word garden, though in a "liberated" sense, to describe these synthetic constructions.'
    ), '主题：无家可归者的花园与人类精神需求。', ['人文关怀', '社会问题']),
    (2012, '学术短文翻译', (
        '(46) In physics, one approach takes this impulse for unification to its extreme, and seeks a theory of everything — a single generative equation for all we see. '
        '(47) Here, Darwinism seems to offer justification, for if all humans share common origins, it seems reasonable to suppose that cultural diversity could also be traced to more constrained beginnings. '
        '(48) To filter out what is unique from what is shared might enable us to understand how complex cultural behavior arose and what guides it in evolutionary or cognitive terms. '
        '(49) The second, by Joshua Greenberg, takes a more empirical approach to universality, identifying traits (particularly in word order) shared by many languages, which are considered to represent biases that result from cognitive constraints. '
        '(50) Chomsky\'s grammar should show patterns of language change that are independent of the family tree or the pathway tracked through it, whereas Greenbergian universality predicts strong co-dependencies between particular types of word-order relations.'
    ), '主题：语言普遍性理论与文化演化。', ['语言学', '科学理论']),
    (2011, '学术短文翻译', (
        '(46) Allen\'s contribution was to take an assumption we all share — that because we are not robots we therefore control our thoughts — and reveal its erroneous nature. '
        '(47) While we may be able to sustain the illusion of control through the conscious mind alone, in reality we are continually faced with a question: "Why cannot I make myself do this or achieve that?" '
        '(48) This seems a justification for neglect of those in need, and a rationalization of exploitation, of the superiority of those at the top and the inferiority of those at the bottom. '
        '(49) Circumstances seem to be designed to bring out the best in us, and if we feel that we have been "wronged" then we are unlikely to begin a conscious effort to escape from our situation. '
        '(50) The upside is the possibilities contained in knowing that everything is up to us; where before we were experts in the array of limitations, now we become authorities of what is possible.'
    ), '主题：詹姆斯·艾伦《做你想做的人》的思想内核。', ['哲学思想', '个人成长']),
    (2010, '学术短文翻译', (
        '(46) Scientists jumped to the rescue with some distinctly shaky evidence to the effect that insects would eat us up if birds failed to control them. '
        '(47) But we have at least drawn nearer the point of admitting that birds should continue as a matter of intrinsic right, regardless of the presence or absence of economic advantage to us. '
        '(48) Time was when biologists somewhat overworked the evidence that these creatures preserve the health of game by killing the physically weak, or that they prey only on "worthless" species. '
        '(49) In Europe, where forestry is ecologically more advanced, the non-commercial tree species are recognized as members of native forest community, to be preserved as such, within reason. '
        '(50) It tends to ignore, and thus eventually to eliminate, many elements in the land community that lack commercial value, but that are essential to its healthy functioning.'
    ), '主题：生态系统的经济价值。', ['生态保护', '自然经济']),
    (2009, '学术短文翻译', (
        '(46) It may be said that the measure of the worth of any social institution is its effect in enlarging and improving experience; but this effect is not a part of its original motive. '
        '(47) Only gradually was the by-product of the institution noted, and only more gradually still was this effect considered as a directive factor in the conduct of the institution. '
        '(48) While it is easy to ignore in our contact with them the effect of our acts upon their disposition, it is not so easy as in dealing with adults. '
        '(49) Since our chief business with them is to enable them to share in a common life we cannot help considering whether or no we are forming the powers which will secure this ability. '
        '(50) We are thus led to distinguish, within the broad educational process which we have been so far considering, a more formal kind of education — that of direct tuition or schooling.'
    ), '主题：广义教育与正规学校教育的区别。', ['教育理论', '教育思想']),
    (2008, '学术短文翻译', (
        '(46) He believes that this very difficulty may have had the compensating advantage of forcing him to think long and intently about every sentence, and thus enabling him to detect errors in reasoning and in his own observations. '
        '(47) He asserted, also, that his power to follow a long and purely abstract train of thought was very limited, for which reason he felt certain that he never could have succeeded with mathematics. '
        '(48) On the other hand, he did not accept as well founded the charge made by some of his critics that, while he was a good observer, he had no power of reasoning. '
        '(49) He adds humbly that perhaps he was "superior to the common run of men in noticing things which easily escape attention, and in observing them carefully." '
        '(50) Darwin was convinced that the loss of these tastes was not only a loss of happiness, but might possibly be injurious to the intellect, and more probably to the moral character.'
    ), '主题：达尔文的思维方式与智力特点。', ['科学家传记', '思维方法']),
    (2007, '学术短文翻译', (
        '(46) Traditionally, legal learning has been viewed in such institutions as the special preserve of lawyers, rather than a necessary part of the intellectual equipment of an educated person. '
        '(47) Happily, the older and more continental view of legal education is establishing itself in a number of Canadian universities and some have even begun to offer undergraduate degrees in law. '
        '(48) If the study of law is beginning to establish itself as part and parcel of a general education, its aims and methods should appeal directly to journalism educators. '
        '(49) In fact, it is difficult to see how journalists who do not have a clear grasp of the basic features of the Canadian Constitution can do a competent job on political stories. '
        '(50) While comment and reaction from lawyers may enhance stories, it is preferable for journalists to rely on their own notions of significance and make their own judgments.'
    ), '主题：加拿大法律教育与新闻业素养。', ['法学教育', '新闻传媒']),
    (2006, '学术短文翻译', (
        '(46) I shall define him as an individual who has elected the activity of thinking in Socratic way about moral problems as his primary duty and pleasure in life. '
        '(47) His function is analogous to that of a judge, who must accept the obligation of revealing in as obvious a manner as possible the course of reasoning which led him to his decision. '
        '(48) I have excluded him because, while his accomplishments may contribute to the solution of moral problems, he has not been charged with the task of approaching any but the factual aspects of those problems. '
        '(49) But his primary task is not to think about the moral code which governs his activity, any more than a businessman is expected to dedicate his energies to an exploration of rules of conduct in business. '
        '(50) They may teach very well, and more than earn their salaries, but most of them make little or no independent reflections on human problems which involve moral judgment.'
    ), '主题：美国知识分子的社会角色与定义。', ['社会角色', '知识分子']),
]
E2_TRANSLATION = [
    (2026, '段落翻译', (
        'The influence of wearables on psychology refers to how the clothes we wear affect our thoughts, feelings, and behaviors. Clothing is not just about covering our bodies; it plays a significant role in shaping our self-perception and interactions with others. '
        'One aspect of this influence is self-expression. The clothes we choose can reflect our personality, mood, and identity. Whether we opt for bold, colorful outfits or prefer more understated styles, our dress choices convey messages about who we are and how we want to be perceived. Additionally, clothing can impact our confidence levels. When we wear clothes that make us feel comfortable and confident, it can positively affect our self-esteem and overall mood. '
        'Moreover, cultural and social influences play a significant role in shaping our dress choices. Different cultures have their norms and expectations regarding dress, which can influence the types of clothing people wear and the meanings attributed to them.'
    ), '主题：着装对心理的影响（穿衣认知效应）。', ['心理效应', '社会生活']),
    (2025, '段落翻译', (
        'You know the moment — the conversation slows, then there\'s a pause. It\'s awkward, so awkward that some people will panic and say anything. Do we all find such silences so stressful? '
        'Researchers analyzed the frequency and impact of gaps greater than 2 seconds during conversations, and previous studies indicate that the fear of awkward silences can be so extreme that people avoid talking to strangers. '
        'During conversations with short gaps, feelings of connection stay strong. But such feelings of connection markedly dip when entering a long gap. Long gaps between strangers are likely to be followed by a change in topic. But the opposite seems to be true for conversations between friends, who often use silences as a comfortable, natural part of talking.'
    ), '主题：对话中的停顿现象与社交心理。\n参考译文：你知道那种时刻吧——谈话慢了下来，然后出现了停顿。这种场面令人尴尬，尴尬到让一些人惊慌失措，只能随便说些什么。我们都认为这样的沉默让人倍感压力吗？研究者们分析了谈话期间超过2秒的停顿的发生率及影响，先前的研究表明，人们太过担心尴尬的沉默，以至于他们会避免和陌生人交谈。在有短暂停顿的谈话中，人们感觉彼此的联系依然紧密。然而，当谈话陷入长时间的停顿时，这种联系感会显著降低。陌生人之间谈话的长时间停顿易于引发话题的转换。但是，对于朋友之间的谈话，情况似乎恰好相反，朋友常把沉默当作交谈中舒适、自然的一部分。', ['心理研究', '社会交际']),
    (2024, '段落翻译', (
        'With the smell of coffee and fresh bread floating in the air, stalls bursting with colourful vegetables and tempting cheeses, and the buzz of friendly chats, farmers markets are a feast for the senses. '
        'They also provide an opportunity to talk to the people responsible for growing or raising your food, support your local economy and pick up fresh seasonal produce — all at the same time. '
        'Farmers\' markets are usually weekly or monthly events, most often with outdoor stalls, which allow farmers or producers to sell their food directly to customers. The size or regularity of markets can vary from season to season, depending on the area\'s agricultural calendar, and you\'re likely to find different produce on sale at different times of the year.'
    ), '主题：农贸市场与本地饮食文化。', ['饮食文化', '地方经济']),
    (2023, '段落翻译', (
        'William Wordsworth is one of Britain\'s most famous poets, and he is often credited with starting the Romantic movement in English literature. Born in 1770 in the Lake District, he grew up surrounded by the dramatic mountains and lakes that would become the central inspiration for his work. '
        'Unlike many poets of his time, who wrote about grand historical events or mythical heroes, Wordsworth focused on ordinary people and everyday experiences, and he believed that poetry should be written in the simple language of common speech. '
        'His most famous work, The Prelude, is a long autobiographical poem that explores the development of his own mind and his relationship with nature. Even today, his poems continue to be loved for their quiet beauty and their deep appreciation for the natural world.'
    ), '主题：英国诗人华兹华斯与自然诗歌。', ['文学名人', '自然诗歌']),
    (2022, '段落翻译', (
        'Drawing and painting are often seen as hobbies for talented people, but research shows that they offer powerful benefits for mental health, regardless of skill level. '
        'First, creative expression reduces stress and anxiety by providing a distraction from negative thoughts and allowing emotions to be processed in a non-verbal way. Second, it improves focus and concentration, similar to meditation, as the mind becomes fully absorbed in the task. '
        'Third, making art boosts self-esteem and provides a sense of accomplishment. Fourth, it encourages mindfulness and helps people stay present in the moment. Other benefits include improved memory, better problem-solving skills, and stronger social connections when creating art with others.'
    ), '主题：绘画对心理健康的七大益处。', ['心理健康', '艺术疗愈']),
    (2021, '段落翻译', (
        'We tend to think that strangers are uninterested in talking to us, but research suggests the opposite is true: most people actually enjoy having conversations with people they don\'t know. '
        'Studies have found that talking to strangers can boost our mood, reduce loneliness, and even improve our sense of belonging. Many people avoid these interactions because they fear rejection or awkward silences, but those fears are usually unfounded. '
        'Even short, casual exchanges — like a quick chat with a barista or a neighbour — can have a positive effect on our well-being. They remind us that we are part of a larger community, and they can make ordinary days feel a little brighter.'
    ), '主题：与陌生人交谈的益处。', ['社会心理', '人际关系']),
    (2020, '段落翻译', (
        'It\'s almost impossible to go through life without experiencing some kind of failure. People who do so probably live so cautiously that they go nowhere. Put simply, they\'re not really living at all. '
        'But the wonderful thing about failure is that it\'s entirely up to us to decide how to look at it. We can choose to see failure as "the end of the world", or as proof of just how inadequate we are. Or, we can look at failure as the incredible learning experience that it often is. '
        'Every time we fail at something, we can choose to look for the lesson we\'re meant to learn. These lessons are very important; they\'re how we grow, and how we keep from making that same mistake again. Failures stop us only if we let them.'
    ), '主题：克服对失败的恐惧。', ['人生哲理', '心理成长']),
    (2019, '段落翻译', (
        'James Herriot was a British veterinarian and writer who became famous for his semi-autobiographical books about rural life and animal care. Born in 1916, he grew up in Scotland and trained as a vet in Glasgow before moving to the Yorkshire Dales to work in a rural practice. '
        'His books, which include All Creatures Great and Small, describe his everyday experiences treating farm animals and pets, and they are filled with warm humour and vivid descriptions of the English countryside. '
        'He wrote his first book when he was 50 years old, after being told for years that he should put his stories down on paper. His work became an international bestseller, and it has been adapted for television multiple times, charming audiences around the world.'
    ), '主题：英国作家詹姆斯·赫里奥特的人生。', ['人物传记', '乡村生活']),
    (2018, '段落翻译', (
        'A fifth grader gets a homework assignment to select his future career path from a list of occupations. He ticks "astronaut" but quickly adds "scientist" to the list and selects it as well. The boy is convinced that if he reads enough, he can explore as many career paths as he likes. And so he reads — everything from encyclopedias to science fiction novels. He reads so passionately that his parents have to institute a "no reading policy" at the dinner table. '
        'That boy was Bill Gates, and he hasn\'t stopped reading yet — not even after becoming one of the most successful people on the planet. Nowadays, his reading material has changed from science fiction and reference books: recently, he revealed that he reads at least 50 nonfiction books a year. Gates chooses nonfiction titles because they explain how the world works.'
    ), '主题：比尔·盖茨的阅读习惯。', ['名人轶事', '阅读习惯']),
    (2017, '段落翻译', (
        'My dream has always been to work somewhere in an area between fashion and publishing. Two years before graduating from secondary school, I took a sewing and design course thinking that I would move on to a fashion design course. '
        'However, during that course I realized I was not good enough in this area to compete with other creative personalities in the future, so I decided that it was not the right path for me. Before applying for university I told everyone that I would study journalism, because writing was, and still is, one of my favorite activities. '
        'But, to be honest, I said it, because I thought that fashion and me together was just a dream — I knew that no one could imagine me in the fashion industry at all! So I decided to look for some fashion-related courses that included writing. This is when I noticed the course "Fashion Media & Promotion".'
    ), '主题：追逐时尚行业的梦想。', ['职业梦想', '个人成长']),
    (2016, '段落翻译', (
        'The supermarket is designed to lure customers into spending as much time as possible within its doors. The reason for this is simple: The longer you stay in the store, the more stuff you\'ll see, and the more stuff you see, the more you\'ll buy. '
        'And supermarkets contain a lot of stuff. The average supermarket, according to the Food Marketing Institute, carries some 44,000 different items, and many carry tens of thousands more. The sheer volume of available choice is enough to send shoppers into a state of information overload. '
        'According to brain-scan experiments, the demands of so much decision-making quickly become too much for us. After about 40 minutes of shopping, most people stop struggling to be rationally selective, and instead begin shopping emotionally — which is the point at which we accumulate the 50 percent of stuff in our cart that we never intended buying.'
    ), '主题：超市消费心理学。', ['消费心理', '市场营销']),
    (2015, '段落翻译', (
        'When you travel on a familiar route, whether it is the way to work or the way to the shops, it may seem as if the distance is shorter than it really is. This is called the "well-travelled road effect", and it is a common cognitive bias that affects almost everyone. '
        'The reason for this effect is that when we are travelling along a familiar path, we don\'t pay as much attention to our surroundings, so the journey seems to pass more quickly. '
        'Researchers at the University of Kyushu in Japan asked people to walk the same route repeatedly, and they found that people consistently overestimated how long it took to walk a familiar route at the end of the trip and underestimated it at the beginning. The reverse was found for unfamiliar routes: people underestimated how long the trip would take at the beginning and overestimated it at the end.'
    ), '主题："熟路效应"的认知心理。', ['认知心理', '行为科学']),
    (2014, '段落翻译', (
        'Most people would define optimism as being endlessly happy, with a glass that\'s perpetually half full. But that\'s exactly the kind of false cheerfulness that positive psychologists wouldn\'t recommend. '
        '"Healthy optimism means being in touch with reality," says Tal Ben-Shahar, a Harvard professor. According to Ben-Shahar, realistic optimists are those who make the best of things that happen, but not those who believe everything happens for the best. '
        'Ben-Shahar uses three optimistic exercises. When he feels down — say, after giving a bad lecture — he grants himself permission to be human. He reminds himself that not every lecture can be a Nobel winner; some will be less effective than others. Next is reconstruction. He analyzes the weak lecture, learning lessons for the future about what works and what doesn\'t. Finally, there is perspective, which involves acknowledging that in the grand scheme of life, one bad lecture really doesn\'t matter.'
    ), '主题：乐观主义的正确认知。', ['心理学', '人生哲理']),
    (2013, '段落翻译', (
        'I can pick a date from the past 53 years and know instantly where I was, what happened in the news and even the day of the week. I\'ve been able to do this since I was four. '
        'I never feel overwhelmed with the amount of information my brain absorbs. My mind seems to be able to cope and the information is stored away neatly. When I think of a sad memory, I do what everybody does — try to put it to one side. I don\'t think it\'s harder for me just because my memory is clearer. Powerful memory doesn\'t make my emotions any more acute or vivid. '
        'I can recall the day my grandfather died and the sadness I felt the day before when we visited him in hospital. I also remember that the musical Hair opened on Broadway on the same day — they both just pop into my mind in the same way.'
    ), '主题：人类的时间感知与记忆能力。', ['记忆心理', '认知科学']),
    (2012, '段落翻译', (
        'When people in developing countries worry about migration, they are usually concerned at the prospect of their best and brightest departure to Silicon Valley or to hospitals and universities in the developed world. These are the kind of workers that countries like Britain, Canada and Australia try to attract by using immigration rules that privilege college graduates. '
        'Lots of studies have found that well-educated people from developing countries are particularly likely to emigrate. A big survey of Indian households in 2004 found that nearly 40% of emigrants had more than a high-school education, compared with around 3.3% of all Indians over the age of 25. '
        'This "brain drain" has long bothered policymakers in poor countries. They fear that it hurts their economies, depriving them of much-needed skilled workers who could have taught at their universities, worked in their hospitals and come up with clever new products for their factories to make.'
    ), '主题：发展中国家的人才流失。', ['人才流动', '经济问题']),
    (2011, '段落翻译', (
        'Who would have thought that, globally, the IT industry produces about the same volume of greenhouse gases as the world\'s airlines do — roughly 2 percent of all CO₂ emissions? '
        'Many everyday tasks take a surprising toll on the environment. A Google search can leak between 0.2 and 7.0 grams of CO₂, depending on how many attempts are needed to get the "right" answer. At the upper end of the scale, two searches create roughly the same emissions as boiling a kettle. '
        'To deliver results to its users quickly, Google has to maintain vast data centres around the world, packed with powerful computers. As well as producing large quantities of CO₂, these computers emit a great deal of heat, so the centres need to be well air-conditioned — which uses even more energy. '
        'However, Google and other big tech providers monitor their efficiency closely and make improvements. Monitoring is the first step on the road to reduction, but there\'s much more to be done, and not just by big companies.'
    ), '主题：IT 行业的碳排放与环境影响。', ['科技环保', '碳排放']),
    (2010, '段落翻译', (
        '"Sustainability" has become a popular word these days, but to Ted Ning, the concept will always have personal meaning. Having endured a painful period of unsustainability in his own life made it clear to him that sustainability-oriented values must be expressed through everyday action and choice. '
        'Ning recalls spending a confusing year in the late 1990s selling insurance. He\'d been through the dot-com boom and burst and, desperate for a job, signed on with a Boulder agency. '
        'It didn\'t go well. "It was a really bad move because that\'s not my passion," says Ning, whose dilemma about the job translated, predictably, into a lack of sales. "I was miserable. I had so much anxiety that I would wake up in the middle of the night and stare at the ceiling. I had no money and needed the job. Everyone said, \'Just wait, you\'ll turn the corner, give it some time.\'"'
    ), '主题：可持续发展理念与个人经历。', ['可持续发展', '个人成长']),
]


def _make_title(exam_type, qtype, genre):
    exam_disp = '英语一' if exam_type == 'english1' else '英语二'
    qtype_disp = '小作文' if qtype == 'small_essay' else ('大作文' if qtype == 'big_essay' else '翻译')
    return f'{exam_disp}{qtype_disp} {genre}' if genre else f'{exam_disp}{qtype_disp}'


def import_questions(verbose=True):
    created = 0
    updated = 0

    def upsert(exam_type, qtype, year, genre, content, tags, prompt=''):
        nonlocal created, updated
        title = _make_title(exam_type, qtype, genre)
        obj, was_created = ExamQuestion.objects.update_or_create(
            exam_type=exam_type, year=year, question_type=qtype,
            defaults={
                'genre': genre,
                'title': title,
                'content': content,
                'prompt': prompt,
                'tags': tags,
                'is_imported': True,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    for year, genre, content, tags in E1_SMALL:
        upsert('english1', 'small_essay', year, genre, content, tags)
    for year, genre, content, tags in E1_BIG:
        upsert('english1', 'big_essay', year, genre, content, tags)
    for year, genre, content, tags in E2_SMALL:
        upsert('english2', 'small_essay', year, genre, content, tags)
    for year, genre, content, tags in E2_BIG:
        upsert('english2', 'big_essay', year, genre, content, tags)
    for year, genre, content, note, tags in E1_TRANSLATION:
        upsert('english1', 'translation', year, genre, content, tags,
               prompt='将文中划线句子翻译成中文（10分，每题2分）\n' + note)
    for year, genre, content, note, tags in E2_TRANSLATION:
        upsert('english2', 'translation', year, genre, content, tags,
               prompt='将下列短文翻译成中文（15分）\n' + note)

    if verbose:
        print(f'导入完成：新增 {created} 条，更新 {updated} 条')
        total = ExamQuestion.objects.count()
        print(f'当前真题总数：{total}')
        print('分布：')
        for et in ['english1', 'english2']:
            for qt in ['small_essay', 'big_essay']:
                cnt = ExamQuestion.objects.filter(exam_type=et, question_type=qt).count()
                print(f'  {et} - {qt}: {cnt}')


class Command(BaseCommand):
    help = '导入考研英语作文真题（英语一/英语二，2006-2025）'

    def handle(self, *args, **options):
        import_questions()