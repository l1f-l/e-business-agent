"""模拟评论语料：每个商品 6-8 条，好评差评都真实存在。

设计约束（直接决定 RAG 效果）：
1. 每条评论都带结构化的 pros/cons 短标签，聚合时按标签计数，不靠模型自己归纳；
2. 差评必须落在具体场景上（"戴久了夹耳朵""地铁里听不清"），空泛的"不好用"检索不到；
3. 评分与情绪一致：>=4 正面，=3 中性，<=2 负面——前端按这个染色。
"""
from __future__ import annotations

from collections import Counter
from typing import Any

REVIEWS: list[dict[str, Any]] = [
    # ---------- p01 星火 X5 ----------
    {"id": "p01-r1", "product_id": "p01", "author": "拍照的阿哲", "rating": 5, "date": "2026-08-12", "helpful": 156,
     "text": "夜景真的顶，演唱会坐看台用 5 倍长焦能看清人脸，朋友圈直接出片，不用再背相机了。",
     "pros": ["拍照强", "长焦实用"], "cons": []},
    {"id": "p01-r2", "product_id": "p01", "author": "追剧小陈", "rating": 4, "date": "2026-08-20", "helpful": 43,
     "text": "1.5K 曲面屏看剧很通透，色彩也舒服。就是 220g 拿久了手腕发酸，躺床上刷得两只手换着拿。",
     "pros": ["屏幕好"], "cons": ["机身偏重"]},
    {"id": "p01-r3", "product_id": "p01", "author": "手游老张", "rating": 3, "date": "2026-09-02", "helpful": 88,
     "text": "拍照没得说，但玩原神半小时背面就烫手，帧率从 60 掉到 45 左右，夏天得摘壳。",
     "pros": ["拍照强"], "cons": ["发热明显", "游戏掉帧"]},
    {"id": "p01-r4", "product_id": "p01", "author": "通勤族Lily", "rating": 5, "date": "2026-09-11", "helpful": 61,
     "text": "早上八点满电出门，晚上十点还剩 30% 多，80W 充半小时能到 80%，续航和快充都省心。",
     "pros": ["续航够用", "充电快"], "cons": []},
    {"id": "p01-r5", "product_id": "p01", "author": "极简主义者", "rating": 2, "date": "2026-09-18", "helpful": 132,
     "text": "硬件不错，但系统广告和预装应用太多了，负一屏推新闻，删还删不干净，体验打折扣。",
     "pros": [], "cons": ["系统广告多", "预装应用多"]},
    {"id": "p01-r6", "product_id": "p01", "author": "爱拍娃的爸爸", "rating": 4, "date": "2026-09-25", "helpful": 37,
     "text": "人像虚化边缘很自然，拍孩子跑来跑去也能抓住。夜景模式要端稳两秒，手抖就糊。",
     "pros": ["人像自然", "抓拍快"], "cons": ["夜景需端稳"]},
    {"id": "p01-r7", "product_id": "p01", "author": "曲面屏受害者", "rating": 4, "date": "2026-10-03", "helpful": 29,
     "text": "整体满意，就是曲面屏边缘偶尔误触，打游戏握持的时候会点到返回。",
     "pros": ["屏幕好"], "cons": ["曲面误触"]},

    # ---------- p02 星火 Note 12 ----------
    {"id": "p02-r1", "product_id": "p02", "author": "给爸妈买", "rating": 5, "date": "2026-07-30", "helpful": 204,
     "text": "给爸妈买的，两天一充完全够，微信视频一小时后盖都不热，字大声音大，老人用着顺手。",
     "pros": ["续航强", "适合长辈"], "cons": []},
    {"id": "p02-r2", "product_id": "p02", "author": "外卖骑手小刘", "rating": 4, "date": "2026-08-06", "helpful": 97,
     "text": "跑单一天不用带充电宝，导航十小时还有 40%。充电只有 33W，从零到满要一个多小时。",
     "pros": ["续航强"], "cons": ["充电偏慢"]},
    {"id": "p02-r3", "product_id": "p02", "author": "王者玩家", "rating": 3, "date": "2026-08-19", "helpful": 145,
     "text": "刷视频聊微信很流畅，打王者开高帧会掉到 40 帧，团战有点卡，游戏党慎入。",
     "pros": ["日常流畅"], "cons": ["游戏掉帧"]},
    {"id": "p02-r4", "product_id": "p02", "author": "学生党小吴", "rating": 5, "date": "2026-09-01", "helpful": 72,
     "text": "1299 这个价位挑不出毛病，网课、记笔记、看剧都够，屏幕大看着不累。",
     "pros": ["性价比高", "屏幕大"], "cons": []},
    {"id": "p02-r5", "product_id": "p02", "author": "躺床刷手机", "rating": 2, "date": "2026-09-14", "helpful": 58,
     "text": "199g 是真沉，躺床上单手刷十分钟手腕就酸，砸脸上是真的疼。",
     "pros": [], "cons": ["机身偏重"]},
    {"id": "p02-r6", "product_id": "p02", "author": "广场舞阿姨", "rating": 4, "date": "2026-09-22", "helpful": 41,
     "text": "外放声音很大，跳广场舞放歌够用，就是音质一般，低音有点破。",
     "pros": ["外放响亮"], "cons": ["音质一般"]},

    # ---------- p03 声浪 Air Pro ----------
    {"id": "p03-r1", "product_id": "p03", "author": "地铁通勤八年", "rating": 5, "date": "2026-07-18", "helpful": 312,
     "text": "地铁开降噪，轰隆声基本没了，播客终于能听清。499 这个价位降噪真没对手。",
     "pros": ["降噪强", "性价比高"], "cons": []},
    {"id": "p03-r2", "product_id": "p03", "author": "耳机控老K", "rating": 4, "date": "2026-07-29", "helpful": 188,
     "text": "音质在这个价位算好的，低频有弹性、人声不糊。但戴久了耳道发胀，摘下来要缓一会儿。",
     "pros": ["音质好"], "cons": ["佩戴胀耳"]},
    {"id": "p03-r3", "product_id": "p03", "author": "居家办公阿May", "rating": 2, "date": "2026-08-11", "helpful": 174,
     "text": "听歌没问题，开线上会对方老说听不清，风大的时候全是呼呼声，通话降噪基本没用。",
     "pros": [], "cons": ["通话一般", "风噪明显"]},
    {"id": "p03-r4", "product_id": "p03", "author": "安静爱好者", "rating": 5, "date": "2026-08-24", "helpful": 96,
     "text": "通透模式很自然，戴着跟同事说话不用摘，切换也不突兀。",
     "pros": ["通透自然"], "cons": []},
    {"id": "p03-r5", "product_id": "p03", "author": "小耳道女生", "rating": 3, "date": "2026-09-05", "helpful": 121,
     "text": "降噪确实强，但耳塞只配了三副，我耳道小，最小号还是偏大，戴一小时就疼。",
     "pros": ["降噪强"], "cons": ["耳塞尺寸偏大", "佩戴胀耳"]},
    {"id": "p03-r6", "product_id": "p03", "author": "手游小周", "rating": 4, "date": "2026-09-16", "helpful": 63,
     "text": "蓝牙 5.3 连接很稳，打游戏延迟能接受，没有明显音画不同步。",
     "pros": ["连接稳定", "延迟低"], "cons": []},
    {"id": "p03-r7", "product_id": "p03", "author": "出差党老李", "rating": 4, "date": "2026-09-27", "helpful": 45,
     "text": "单次 8 小时够一趟高铁，充电盒能再充三次，出差一周没带充电线。",
     "pros": ["续航够用"], "cons": []},
    {"id": "p03-r8", "product_id": "p03", "author": "长发及腰", "rating": 3, "date": "2026-10-08", "helpful": 77,
     "text": "触控太灵敏，撩一下头发就暂停或者切歌，后来干脆在 App 里关了触控。",
     "pros": [], "cons": ["触控误触"]},

    # ---------- p04 声浪 Lite ----------
    {"id": "p04-r1", "product_id": "p04", "author": "开会八小时", "rating": 4, "date": "2026-07-21", "helpful": 88,
     "text": "半入耳戴着不胀，开会戴一下午耳朵没感觉，比入耳式舒服太多。",
     "pros": ["佩戴舒适"], "cons": []},
    {"id": "p04-r2", "product_id": "p04", "author": "地铁党", "rating": 3, "date": "2026-08-02", "helpful": 134,
     "text": "没有降噪，地铁里基本听不清，只能把音量调到 80%，听久了耳朵累。",
     "pros": [], "cons": ["无降噪", "嘈杂环境听不清"]},
    {"id": "p04-r3", "product_id": "p04", "author": "学生小郑", "rating": 5, "date": "2026-08-15", "helpful": 51,
     "text": "199 要啥自行车，上网课、听播客完全够用，坏了也不心疼。",
     "pros": ["性价比高"], "cons": []},
    {"id": "p04-r4", "product_id": "p04", "author": "摇滚老炮", "rating": 2, "date": "2026-08-28", "helpful": 72,
     "text": "低音几乎没有，听摇滚像在听收音机，人声也偏薄，音质党别买。",
     "pros": [], "cons": ["低音弱", "音质一般"]},
    {"id": "p04-r5", "product_id": "p04", "author": "夜跑五公里", "rating": 4, "date": "2026-09-09", "helpful": 34,
     "text": "3.8g 很轻，跑步不掉，出汗也不滑，运动戴挺合适。",
     "pros": ["轻便稳固"], "cons": []},
    {"id": "p04-r6", "product_id": "p04", "author": "图书馆常客", "rating": 3, "date": "2026-09-20", "helpful": 26,
     "text": "安静环境下通话有回声，对方能听到自己的声音，会议室用有点尴尬。",
     "pros": [], "cons": ["通话回声"]},
    {"id": "p04-r7", "product_id": "p04", "author": "通勤一小时", "rating": 4, "date": "2026-10-01", "helpful": 19,
     "text": "6 小时续航，通勤加午休够用，充电盒小巧放口袋里不硌。",
     "pros": ["续航够用", "便携"], "cons": []},

    # ---------- p05 声浪 Studio Max ----------
    {"id": "p05-r1", "product_id": "p05", "author": "写代码的猫", "rating": 5, "date": "2026-07-15", "helpful": 176,
     "text": "写代码戴一整天，包耳不夹耳廓，降噪开到中档就能压住空调和键盘声。",
     "pros": ["佩戴舒适", "降噪够用"], "cons": []},
    {"id": "p05-r2", "product_id": "p05", "author": "戴眼镜的阿森", "rating": 3, "date": "2026-07-27", "helpful": 209,
     "text": "音质好但戴久了夹耳朵，戴眼镜更明显，两小时后太阳穴两边压得慌。",
     "pros": ["音质好"], "cons": ["夹头", "戴眼镜不适"]},
    {"id": "p05-r3", "product_id": "p05", "author": "出差飞人", "rating": 5, "date": "2026-08-09", "helpful": 143,
     "text": "40 小时续航，出差一周没充过电，飞机上开降噪发动机声小了一大半。",
     "pros": ["续航强", "降噪够用"], "cons": []},
    {"id": "p05-r4", "product_id": "p05", "author": "南方夏天", "rating": 2, "date": "2026-08-21", "helpful": 118,
     "text": "音质和降噪都行，但夏天戴半小时耳朵就出汗，闷得受不了，只能开空调戴。",
     "pros": [], "cons": ["闷热出汗"]},
    {"id": "p05-r5", "product_id": "p05", "author": "双设备用户", "rating": 4, "date": "2026-09-03", "helpful": 57,
     "text": "电脑和手机双连接很方便，开会时手机来电自动切过去，不用手动断连。",
     "pros": ["双设备方便"], "cons": []},
    {"id": "p05-r6", "product_id": "p05", "author": "头围偏大", "rating": 3, "date": "2026-09-15", "helpful": 64,
     "text": "头梁偏紧，我头围 60 戴久了压头顶，建议头大的先去线下试。",
     "pros": [], "cons": ["头梁偏紧"]},
    {"id": "p05-r7", "product_id": "p05", "author": "老AirPro用户", "rating": 4, "date": "2026-09-26", "helpful": 38,
     "text": "降噪比 Air Pro 弱一点，但耳压感轻很多，长时间戴不头晕。",
     "pros": ["耳压轻"], "cons": ["降噪稍弱"]},

    # ---------- p06 极光 Book 14 ----------
    {"id": "p06-r1", "product_id": "p06", "author": "通勤设计师", "rating": 5, "date": "2026-07-19", "helpful": 132,
     "text": "1.28kg 背一天不累，2.8K 屏色彩准，改图做 PPT 都舒服，开会带出去也有面子。",
     "pros": ["轻薄便携", "屏幕好"], "cons": []},
    {"id": "p06-r2", "product_id": "p06", "author": "要接投影", "rating": 4, "date": "2026-08-01", "helpful": 86,
     "text": "机器很满意，但只有两个雷电口，接投影必须带扩展坞，出差多带一个配件有点烦。",
     "pros": ["轻薄便携"], "cons": ["接口少"]},
    {"id": "p06-r3", "product_id": "p06", "author": "剪片新手", "rating": 3, "date": "2026-08-14", "helpful": 94,
     "text": "剪 4K 时间线会卡，加特效就掉帧，核显还是不够，想剪视频得加钱上独显。",
     "pros": [], "cons": ["性能不足"]},
    {"id": "p06-r4", "product_id": "p06", "author": "会议达人", "rating": 5, "date": "2026-08-26", "helpful": 61,
     "text": "开一天会记笔记、放 PPT，晚上回酒店还有 30% 电，续航真的顶。",
     "pros": ["续航强"], "cons": []},
    {"id": "p06-r5", "product_id": "p06", "author": "码字工", "rating": 2, "date": "2026-09-07", "helpful": 73,
     "text": "键程太短，敲一天文档手指发酸，键盘手感不如我五年前的老本。",
     "pros": [], "cons": ["键盘手感差"]},
    {"id": "p06-r6", "product_id": "p06", "author": "办公室靠窗", "rating": 4, "date": "2026-09-19", "helpful": 32,
     "text": "屏幕很细腻，就是镜面屏反光，靠窗坐得调角度，贴了雾面膜才好点。",
     "pros": ["屏幕好"], "cons": ["屏幕反光"]},

    # ---------- p07 极光 Game 16 ----------
    {"id": "p07-r1", "product_id": "p07", "author": "FPS玩家", "rating": 5, "date": "2026-07-22", "helpful": 221,
     "text": "2K 165Hz 打 FPS 很跟手，3A 中高画质能稳 60 帧以上，这价位性能没得挑。",
     "pros": ["性能强", "屏幕高刷"], "cons": []},
    {"id": "p07-r2", "product_id": "p07", "author": "宿舍党", "rating": 3, "date": "2026-08-04", "helpful": 187,
     "text": "性能没话说，但满载风扇声像吹风机，晚上打游戏被室友投诉了两次。",
     "pros": ["性能强"], "cons": ["风扇噪音大"]},
    {"id": "p07-r3", "product_id": "p07", "author": "建模学生", "rating": 4, "date": "2026-08-17", "helpful": 98,
     "text": "渲染比我旧台式还快，散热压得住，键盘区不烫手。裸机 2.4kg，天天背去教室是真的沉。",
     "pros": ["性能强", "散热好"], "cons": ["机身偏重"]},
    {"id": "p07-r4", "product_id": "p07", "author": "剪辑师阿凯", "rating": 5, "date": "2026-08-29", "helpful": 76,
     "text": "剪 4K 多轨不卡，导出十分钟的片子三分钟搞定，比同价位轻薄本强太多。",
     "pros": ["性能强"], "cons": []},
    {"id": "p07-r5", "product_id": "p07", "author": "图书馆卷王", "rating": 2, "date": "2026-09-10", "helpful": 112,
     "text": "离电只能用一小时多，去图书馆必须抢带插座的位置，电池基本是摆设。",
     "pros": [], "cons": ["续航很短"]},
    {"id": "p07-r6", "product_id": "p07", "author": "色准要求高", "rating": 4, "date": "2026-09-21", "helpful": 44,
     "text": "屏幕色域高，做建模和调色颜色准，出厂校色做得不错。",
     "pros": ["屏幕好"], "cons": []},
    {"id": "p07-r7", "product_id": "p07", "author": "码字兼职", "rating": 3, "date": "2026-10-02", "helpful": 39,
     "text": "打游戏很爽，但键盘手感一般，敲长文不如轻薄本，键程偏软。",
     "pros": [], "cons": ["键盘手感差"]},

    # ---------- p08 极光 Book Air ----------
    {"id": "p08-r1", "product_id": "p08", "author": "预算三千", "rating": 4, "date": "2026-07-25", "helpful": 118,
     "text": "三千块办公本，写文档、上网课、看剧都行，不玩游戏完全够用。",
     "pros": ["性价比高"], "cons": []},
    {"id": "p08-r2", "product_id": "p08", "author": "看剧党", "rating": 3, "date": "2026-08-07", "helpful": 67,
     "text": "屏幕素质一般，颜色发灰，看剧不如我手机，亮度也偏低。",
     "pros": [], "cons": ["屏幕一般"]},
    {"id": "p08-r3", "product_id": "p08", "author": "多标签选手", "rating": 2, "date": "2026-08-20", "helpful": 156,
     "text": "8G 内存真不够用，开十几个网页标签就开始卡，切窗口要等，建议加钱上 16G。",
     "pros": [], "cons": ["内存不足", "多任务卡顿"]},
    {"id": "p08-r4", "product_id": "p08", "author": "学生家长", "rating": 5, "date": "2026-09-02", "helpful": 52,
     "text": "给孩子上大学用，便宜耐造，坏了不心疼，基础作业完全能应付。",
     "pros": ["性价比高"], "cons": []},
    {"id": "p08-r5", "product_id": "p08", "author": "通勤族", "rating": 4, "date": "2026-09-13", "helpful": 28,
     "text": "1.4kg 装包里没负担，续航十小时，出门一天不用带充电器。",
     "pros": ["便携", "续航长"], "cons": []},
    {"id": "p08-r6", "product_id": "p08", "author": "安静办公室", "rating": 3, "date": "2026-09-24", "helpful": 21,
     "text": "偶尔风扇会突然大声转一下，一般办公听不到，但安静会议室里挺明显。",
     "pros": [], "cons": ["风扇噪音"]},

    # ---------- p09 掌阅 Pad 11 ----------
    {"id": "p09-r1", "product_id": "p09", "author": "追剧妈妈", "rating": 5, "date": "2026-07-28", "helpful": 142,
     "text": "11 寸大屏配四扬声器，躺沙发看剧很爽，孩子上网课也够大。",
     "pros": ["屏幕大", "外放好"], "cons": []},
    {"id": "p09-r2", "product_id": "p09", "author": "熬夜看小说", "rating": 4, "date": "2026-08-10", "helpful": 83,
     "text": "护眼模式舒服，看两小时眼睛不酸，晚上躺床上看小说很合适。",
     "pros": ["护眼"], "cons": []},
    {"id": "p09-r3", "product_id": "p09", "author": "想当生产力", "rating": 3, "date": "2026-08-23", "helpful": 97,
     "text": "想拿它替代笔记本的别想了，办公软件功能残缺，Excel 复杂表格打不开宏。",
     "pros": [], "cons": ["办公生态弱"]},
    {"id": "p09-r4", "product_id": "p09", "author": "多任务用户", "rating": 2, "date": "2026-09-04", "helpful": 66,
     "text": "系统偶尔卡顿，分屏开视频加笔记会掉帧，用久了得重启。",
     "pros": [], "cons": ["系统卡顿"]},
    {"id": "p09-r5", "product_id": "p09", "author": "手写笔记党", "rating": 4, "date": "2026-09-16", "helpful": 39,
     "text": "配笔写字跟手，延迟很低，记课堂笔记比纸笔方便，还能直接搜手写内容。",
     "pros": ["手写跟手"], "cons": []},
    {"id": "p09-r6", "product_id": "p09", "author": "长途高铁", "rating": 4, "date": "2026-09-27", "helpful": 31,
     "text": "8000mAh 电池，追剧一整天还有电，高铁上看了六集没充电。",
     "pros": ["续航长"], "cons": []},
    {"id": "p09-r7", "product_id": "p09", "author": "单手党", "rating": 3, "date": "2026-10-06", "helpful": 18,
     "text": "490g 单手拿久了手腕酸，基本得两只手或者架着看。",
     "pros": [], "cons": ["机身偏重"]},

    # ---------- p10 脉动 Watch 3 ----------
    {"id": "p10-r1", "product_id": "p10", "author": "跑步两年", "rating": 5, "date": "2026-07-24", "helpful": 167,
     "text": "两周充一次电，睡眠分期挺准，早上看数据已经成习惯了。",
     "pros": ["续航长", "睡眠监测准"], "cons": []},
    {"id": "p10-r2", "product_id": "p10", "author": "心率带老用户", "rating": 4, "date": "2026-08-05", "helpful": 74,
     "text": "跑步心率跟胸带对比差 3-5 下，日常训练够用，专业训练还是戴胸带。",
     "pros": ["心率够准"], "cons": []},
    {"id": "p10-r3", "product_id": "p10", "author": "想回微信", "rating": 2, "date": "2026-08-18", "helpful": 121,
     "text": "第三方 App 太少，微信只能看通知不能回，支付也不支持，智能体验差点意思。",
     "pros": [], "cons": ["应用生态少"]},
    {"id": "p10-r4", "product_id": "p10", "author": "泳池常客", "rating": 5, "date": "2026-08-30", "helpful": 58,
     "text": "游泳戴着没问题，50 米池来回记圈挺准，5ATM 不是虚标的。",
     "pros": ["防水可靠"], "cons": []},
    {"id": "p10-r5", "product_id": "p10", "author": "户外跑步", "rating": 3, "date": "2026-09-11", "helpful": 47,
     "text": "太阳底下屏幕看不清，得用手挡一下，亮度不够。",
     "pros": [], "cons": ["强光下看不清"]},
    {"id": "p10-r6", "product_id": "p10", "author": "睡觉戴表", "rating": 4, "date": "2026-09-22", "helpful": 26,
     "text": "表带亲肤，戴着睡觉不硌手，翻身也没异物感。",
     "pros": ["佩戴舒适"], "cons": []},
    {"id": "p10-r7", "product_id": "p10", "author": "路跑新手", "rating": 3, "date": "2026-10-04", "helpful": 33,
     "text": "GPS 搜星慢，出门要站在楼下等半分钟才开始记，跑起来才准。",
     "pros": [], "cons": ["GPS 搜星慢"]},
]

REVIEW_MAP = {r["id"]: r for r in REVIEWS}

BY_PRODUCT: dict[str, list[dict[str, Any]]] = {}
for _review in REVIEWS:
    BY_PRODUCT.setdefault(_review["product_id"], []).append(_review)


def sentiment_of(rating: int) -> str:
    if rating >= 4:
        return "positive"
    if rating == 3:
        return "neutral"
    return "negative"


def to_document(review: dict[str, Any]) -> str:
    """评论向量化文本：带上商品名，跨商品语义检索才分得清主体。"""
    from app.rag.products import PRODUCT_MAP

    product = PRODUCT_MAP.get(review["product_id"], {"name": review["product_id"]})
    return (
        f"商品：{product['name']}\n"
        f"评分：{review['rating']} 星\n"
        f"评价内容：{review['text']}\n"
        f"优点：{'、'.join(review['pros']) or '无'}\n"
        f"缺点：{'、'.join(review['cons']) or '无'}"
    )


def public_review(review: dict[str, Any], score: float | None = None) -> dict[str, Any]:
    data = {
        "id": review["id"],
        "product_id": review["product_id"],
        "author": review["author"],
        "rating": review["rating"],
        "date": review["date"],
        "text": review["text"],
        "sentiment": sentiment_of(review["rating"]),
        "helpful": review.get("helpful", 0),
    }
    if score is not None:
        data["score"] = round(float(score), 4)
    return data


def summarize(product_id: str, matched: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """商品级口碑聚合：用全量评论算均分，用命中的评论给"原声"。

    聚合标签来自预标注的 pros/cons，不经过模型，保证可追溯。
    """
    all_reviews = BY_PRODUCT.get(product_id, [])
    if not all_reviews:
        return {"product_id": product_id, "count": 0, "rating_avg": None, "pros": [], "cons": [], "items": []}

    pros_counter: Counter[str] = Counter()
    cons_counter: Counter[str] = Counter()
    # 逐条统计：3 星评价也可能夸降噪，只按"评论里写了什么"计数，不按星级过滤
    for review in all_reviews:
        pros_counter.update(review["pros"])
        cons_counter.update(review["cons"])

    distribution = Counter(r["rating"] for r in all_reviews)
    rating_avg = round(sum(r["rating"] for r in all_reviews) / len(all_reviews), 1)
    chosen = matched if matched else [r for r in all_reviews if r["rating"] in (5, 4, 2, 3)][:6]

    return {
        "product_id": product_id,
        "count": len(all_reviews),
        "rating_avg": rating_avg,
        "distribution": {str(k): distribution.get(k, 0) for k in range(1, 6)},
        "pros": [{"label": label, "count": n} for label, n in pros_counter.most_common(4)],
        "cons": [{"label": label, "count": n} for label, n in cons_counter.most_common(4)],
        "items": [public_review(r) for r in chosen[:5]],
        "negative": [
            {"id": r["id"], "text": r["text"], "rating": r["rating"]}
            for r in all_reviews
            if r["rating"] <= 3
        ][:3],
    }
