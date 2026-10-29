"""10 个模拟商品。文档文本要写"人话"，向量召回才准。"""
from __future__ import annotations

from typing import Any

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": "p01",
        "name": "星火 X5",
        "brand": "星火",
        "category": "手机",
        "price": 3299,
        "tagline": "2 亿像素影像旗舰，夜景也能拍清",
        "highlights": ["2 亿像素主摄", "潜望长焦 5 倍光变", "骁龙 8 系芯片", "5500mAh 电池"],
        "audience": "爱拍照、拍视频、追剧的年轻人",
        "selling_point": "主打拍照和屏幕。夜景人像噪点控制好，长焦拍演唱会、拍孩子演出很实用；"
        "1.5K 曲面屏看视频通透。机身略重，长时间单手握持会累。",
        "specs": {"屏幕": "6.78 英寸 1.5K", "存储": "12GB+256GB", "快充": "80W"},
        "stock": 42,
        "rating": 4.8,
        "image": "/products/p01.svg",
        "tags": ["拍照", "旗舰", "长焦", "夜景"],
    },
    {
        "id": "p02",
        "name": "星火 Note 12",
        "brand": "星火",
        "category": "手机",
        "price": 1299,
        "tagline": "6000mAh 大电池，两天一充",
        "highlights": ["6000mAh 大电池", "33W 快充", "6.7 英寸大屏", "支持 5G"],
        "audience": "学生党、给长辈买、当备用机",
        "selling_point": "续航是最大卖点，中度使用能撑两天，外卖、跑业务的人不用总找充电宝。"
        "性能只够日常刷视频、聊微信，玩大型游戏会掉帧。",
        "specs": {"屏幕": "6.7 英寸 LCD", "存储": "8GB+128GB", "重量": "199g"},
        "stock": 130,
        "rating": 4.6,
        "image": "/products/p02.svg",
        "tags": ["长续航", "千元机", "学生", "备用机"],
    },
    {
        "id": "p03",
        "name": "声浪 Air Pro",
        "brand": "声浪",
        "category": "耳机",
        "price": 499,
        "tagline": "48dB 主动降噪，通勤地铁安静一半",
        "highlights": ["48dB 主动降噪", "通透模式", "单次续航 8 小时", "蓝牙 5.3 低延迟"],
        "audience": "通勤族、办公室、宿舍学习",
        "selling_point": "五百元价位少见的强降噪，地铁、公交、飞机低频噪音压得很干净，开降噪听歌音量不用调大。"
        "入耳式硅胶耳塞久戴会有压迫感，通话降噪一般。",
        "specs": {"类型": "入耳式 TWS", "续航": "8h + 32h", "防水": "IPX4"},
        "stock": 88,
        "rating": 4.7,
        "image": "/products/p03.svg",
        "tags": ["降噪", "入耳式", "通勤", "蓝牙耳机"],
    },
    {
        "id": "p04",
        "name": "声浪 Lite",
        "brand": "声浪",
        "category": "耳机",
        "price": 199,
        "tagline": "半入耳不闷耳，百元档听个响",
        "highlights": ["半入耳设计", "13mm 动圈", "续航 6 小时", "轻至 3.8g"],
        "audience": "预算有限、戴不惯入耳式的人",
        "selling_point": "半入耳戴着不胀耳，适合长时间开会、听播客。没有主动降噪功能，"
        "地铁、公交这种嘈杂环境里听不清，安静场景用才合适。",
        "specs": {"类型": "半入耳 TWS", "续航": "6h + 18h", "防水": "IPX4"},
        "stock": 210,
        "rating": 4.3,
        "image": "/products/p04.svg",
        "tags": ["半入耳", "百元", "轻便"],
    },
    {
        "id": "p05",
        "name": "声浪 Studio Max",
        "brand": "声浪",
        "category": "耳机",
        "price": 899,
        "tagline": "头戴式降噪，戴一天耳朵不疼",
        "highlights": ["头戴包耳式", "42dB 主动降噪", "续航 40 小时", "双设备连接"],
        "audience": "长时间办公、居家办公、飞行出差",
        "selling_point": "包耳式不压耳廓，写代码、写方案戴一整天也还行。降噪比 Air Pro 略弱但更舒适，"
        "夏天戴会闷热，出门携带占地方。",
        "specs": {"类型": "头戴式", "续航": "40h", "重量": "255g"},
        "stock": 36,
        "rating": 4.6,
        "image": "/products/p05.svg",
        "tags": ["头戴式", "降噪", "办公", "长续航"],
    },
    {
        "id": "p06",
        "name": "极光 Book 14",
        "brand": "极光",
        "category": "笔记本",
        "price": 4599,
        "tagline": "1.28kg 轻薄本，2.8K 高色域屏",
        "highlights": ["1.28kg 轻至", "2.8K 90Hz 高色域屏", "16GB+512GB", "65W 快充"],
        "audience": "经常出差的职场人、文科/商科学生",
        "selling_point": "背着通勤不累，屏幕色彩准，做 PPT、改文档、看片都舒服。"
        "核显，剪 4K 视频和跑大型软件会吃力。",
        "specs": {"屏幕": "14 英寸 2.8K", "重量": "1.28kg", "接口": "双雷电 4"},
        "stock": 27,
        "rating": 4.7,
        "image": "/products/p06.svg",
        "tags": ["轻薄", "办公", "高色域", "便携"],
    },
    {
        "id": "p07",
        "name": "极光 Game 16",
        "brand": "极光",
        "category": "笔记本",
        "price": 7999,
        "tagline": "RTX 独显游戏本，2K 165Hz 高刷",
        "highlights": ["RTX 4060 独显", "2K 165Hz 电竞屏", "双风扇四热管", "16GB+1TB"],
        "audience": "打游戏、做 3D 建模、剪视频的学生和创作者",
        "selling_point": "3A 大作中高画质能跑满帧，建模渲染也扛得住。满载风扇声明显，"
        "裸机 2.4kg，天天背着上课会比较沉。",
        "specs": {"屏幕": "16 英寸 2K 165Hz", "显卡": "RTX 4060", "重量": "2.4kg"},
        "stock": 15,
        "rating": 4.8,
        "image": "/products/p07.svg",
        "tags": ["游戏本", "独显", "高刷", "性能"],
    },
    {
        "id": "p08",
        "name": "极光 Book Air",
        "brand": "极光",
        "category": "笔记本",
        "price": 2999,
        "tagline": "三千档办公本，写文档网课够用",
        "highlights": ["14 英寸 FHD 屏", "8GB+512GB", "续航 10 小时", "1.4kg"],
        "audience": "预算有限的学生、只做表格文档的上班族",
        "selling_point": "性价比取向，Office、网课、看剧都流畅，价格压得很低。"
        "屏幕素质一般，多开十几个网页标签会开始卡。",
        "specs": {"屏幕": "14 英寸 FHD", "重量": "1.4kg", "续航": "10h"},
        "stock": 64,
        "rating": 4.4,
        "image": "/products/p08.svg",
        "tags": ["性价比", "办公", "网课", "入门"],
    },
    {
        "id": "p09",
        "name": "掌阅 Pad 11",
        "brand": "掌阅",
        "category": "平板",
        "price": 1899,
        "tagline": "11 英寸 2.5K 护眼屏，看剧上网课",
        "highlights": ["11 英寸 2.5K 屏", "四扬声器", "8000mAh", "支持手写笔"],
        "audience": "看剧、上网课、给孩子用",
        "selling_point": "屏幕大且护眼，四扬声器外放看剧体验好，配笔能记笔记。"
        "办公软件生态不如笔记本，替代不了电脑。",
        "specs": {"屏幕": "11 英寸 2.5K", "重量": "490g", "电池": "8000mAh"},
        "stock": 51,
        "rating": 4.5,
        "image": "/products/p09.svg",
        "tags": ["平板", "护眼", "网课", "看剧"],
    },
    {
        "id": "p10",
        "name": "脉动 Watch 3",
        "brand": "脉动",
        "category": "手表",
        "price": 799,
        "tagline": "14 天续航，心率血氧全天监测",
        "highlights": ["14 天续航", "心率/血氧监测", "100+ 运动模式", "5ATM 防水"],
        "audience": "跑步健身、关注健康数据的人",
        "selling_point": "两周充一次电，睡眠和心率数据比较稳，游泳可以戴。"
        "第三方 App 少，智能体验比不上手表系统。",
        "specs": {"屏幕": "1.43 英寸 AMOLED", "续航": "14 天", "防水": "5ATM"},
        "stock": 73,
        "rating": 4.5,
        "image": "/products/p10.svg",
        "tags": ["手表", "续航", "运动", "健康"],
    },
]


def to_document(p: dict[str, Any]) -> str:
    """拼成检索用文档：名称、品类、价格、卖点、人群都要出现，命中率才高。"""
    return (
        f"商品名称：{p['name']}\n"
        f"品类：{p['category']}\n"
        f"品牌：{p['brand']}\n"
        f"价格：{p['price']} 元\n"
        f"一句话卖点：{p['tagline']}\n"
        f"核心卖点：{'；'.join(p['highlights'])}\n"
        f"适合人群：{p['audience']}\n"
        f"详细描述：{p['selling_point']}\n"
        f"关键词：{'、'.join(p['tags'])}"
    )


def public(p: dict[str, Any], score: float | None = None) -> dict[str, Any]:
    """给前端的精简结构，字段名稳定，前端不用猜。"""
    data = {
        "id": p["id"],
        "name": p["name"],
        "brand": p["brand"],
        "category": p["category"],
        "price": p["price"],
        "tagline": p["tagline"],
        "highlights": p["highlights"][:3],
        "rating": p.get("rating"),
        "stock": p.get("stock"),
        "image": p.get("image", ""),
    }
    if score is not None:
        data["score"] = round(float(score), 4)
    return data


PRODUCT_MAP = {p["id"]: p for p in PRODUCTS}


# ---------------- 配件：可加购、可推荐，但不进向量语料 ----------------
# 为什么不放进 PRODUCTS：一旦进了集合，"500 元以内降噪耳机"就会召回耳塞套。
# 配件只在「搭配推荐」和购物车里出现，用 LOOKUP_MAP 查价与库存。
ACCESSORIES: list[dict[str, Any]] = [
    {
        "id": "p11",
        "name": "星火 65W 氮化镓快充头",
        "brand": "星火",
        "category": "配件",
        "for_category": "手机",
        "price": 129,
        "stock": 260,
        "rating": 4.7,
        "image": "/products/acc-charger.svg",
        "tagline": "半小时充到 70%，一个头喂饱手机和笔记本",
        "highlights": ["65W 氮化镓", "双口输出", "折叠插脚"],
        "audience": "手机、轻薄本用户",
        "selling_point": "比原装头小一圈，出差只带一个就够；双口同时用会自动分配功率。",
        "tags": ["快充", "氮化镓", "配件"],
    },
    {
        "id": "p12",
        "name": "星火 磁吸防摔壳",
        "brand": "星火",
        "category": "配件",
        "for_category": "手机",
        "price": 89,
        "stock": 310,
        "rating": 4.5,
        "image": "/products/acc-case.svg",
        "tagline": "四角气囊，摔了不心疼",
        "highlights": ["磁吸支持无线充", "四角气囊", "磨砂不沾指纹"],
        "audience": "手滑党、经常外出的人",
        "selling_point": "边框加高护住镜头，磁吸圈不挡无线充；磨砂手感比透明壳耐脏。",
        "tags": ["保护壳", "磁吸", "配件"],
    },
    {
        "id": "p13",
        "name": "声浪 记忆海绵耳塞套",
        "brand": "声浪",
        "category": "配件",
        "for_category": "耳机",
        "price": 39,
        "stock": 420,
        "rating": 4.6,
        "image": "/products/acc-audio.svg",
        "tagline": "换对耳塞，佩戴不胀耳",
        "highlights": ["慢回弹海绵", "三档尺寸", "提升低频密封"],
        "audience": "戴久了耳朵疼、觉得低频不够的用户",
        "selling_point": "慢回弹贴合耳道，长时间佩戴压力更小；密封变好后低频和下潜会明显改善。",
        "tags": ["耳塞套", "舒适", "配件"],
    },
    {
        "id": "p14",
        "name": "声浪 硬壳收纳包",
        "brand": "声浪",
        "category": "配件",
        "for_category": "耳机",
        "price": 59,
        "stock": 180,
        "rating": 4.4,
        "image": "/products/acc-case.svg",
        "tagline": "耳机线材一团糟的解法",
        "highlights": ["EVA 硬壳", "网袋分仓", "可挂包上"],
        "audience": "通勤、健身带耳机的人",
        "selling_point": "硬壳抗压，内部网袋能塞数据线和耳塞套，扔包里不怕压。",
        "tags": ["收纳包", "便携", "配件"],
    },
    {
        "id": "p15",
        "name": "极光 USB-C 七合一扩展坞",
        "brand": "极光",
        "category": "配件",
        "for_category": "笔记本",
        "price": 199,
        "stock": 150,
        "rating": 4.5,
        "image": "/products/acc-desk.svg",
        "tagline": "一个口变七个，外接屏不将就",
        "highlights": ["HDMI 4K60", "PD 100W 回充", "千兆网口"],
        "audience": "轻薄本用户、需要外接显示器的人",
        "selling_point": "轻薄本只有雷电口，接投影、网线、SD 卡全靠它；边用边回充不掉电。",
        "tags": ["扩展坞", "办公", "配件"],
    },
    {
        "id": "p16",
        "name": "极光 14 寸内胆包",
        "brand": "极光",
        "category": "配件",
        "for_category": "笔记本",
        "price": 99,
        "stock": 200,
        "rating": 4.3,
        "image": "/products/acc-case.svg",
        "tagline": "通勤塞进背包，不刮花机身",
        "highlights": ["防泼水外层", "绒面内衬", "前袋收充电器"],
        "audience": "每天背电脑上下班、上课的人",
        "selling_point": "绒面内衬不磨阳极氧化外壳，前袋刚好放充电器和扩展坞。",
        "tags": ["内胆包", "通勤", "配件"],
    },
    {
        "id": "p17",
        "name": "掌阅 磁吸触控笔",
        "brand": "掌阅",
        "category": "配件",
        "for_category": "平板",
        "price": 249,
        "stock": 90,
        "rating": 4.6,
        "image": "/products/acc-desk.svg",
        "tagline": "记笔记、画草图，压感跟手",
        "highlights": ["4096 级压感", "磁吸充电", "延迟 20ms"],
        "audience": "学生、做会议记录的人",
        "selling_point": "写字有摩擦感不打滑，磁吸吸附在平板边上充电，不用单独找线。",
        "tags": ["触控笔", "手写", "配件"],
    },
    {
        "id": "p18",
        "name": "脉动 编织表带",
        "brand": "脉动",
        "category": "配件",
        "for_category": "手表",
        "price": 69,
        "stock": 240,
        "rating": 4.4,
        "image": "/products/acc-audio.svg",
        "tagline": "换条表带，运动出汗也不闷",
        "highlights": ["尼龙编织", "透气速干", "快拆接口"],
        "audience": "运动、夏天佩戴的人",
        "selling_point": "编织材质透气，出汗不粘皮肤；快拆卡扣十秒换带。",
        "tags": ["表带", "运动", "配件"],
    },
]

ACCESSORY_MAP = {a["id"]: a for a in ACCESSORIES}

# 可加购/可引用的全集：商品 + 配件。检索仍只用 PRODUCTS。
LOOKUP_MAP: dict[str, dict[str, Any]] = {**PRODUCT_MAP, **ACCESSORY_MAP}


def product_by_id(product_id: str) -> dict[str, Any] | None:
    return LOOKUP_MAP.get(str(product_id or "").strip().lower())


def accessories_for(category: str | None) -> list[dict[str, Any]]:
    if not category:
        return []
    return [a for a in ACCESSORIES if a.get("for_category") == category]
