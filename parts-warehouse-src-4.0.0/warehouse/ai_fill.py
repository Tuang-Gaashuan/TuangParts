# -*- coding: utf-8 -*-
"""元器件仓库 — AI 快速填入。

用户输入一段自然语言描述（如 "100个 0805 10K 1% 电阻，村田"），
通过用户配置的 AI 接口解析为结构化字段，返回一行数据供写入 Excel。

AI 接口配置见 settings.py (data/settings.json 的 ai 段), 每个使用者填自己的 key。
"""

import json
import os
import re
import httpx

from warehouse.settings import load_settings, DEFAULT_SETTINGS, chat_completions_url

# .env 文件兜底: 项目根 .env (通用) → ~/codex-bridge/.env (兼容作者旧环境)
_ENV_FILE_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    os.path.join(os.path.expanduser("~"), "codex-bridge", ".env"),
]


def _load_key_from_envfile() -> str:
    for p in _ENV_FILE_CANDIDATES:
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEEPSEEK_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            continue
    return ""


def get_api_key(app_dir: str | None = None) -> str:
    """按优先级取 key: 用户配置 > 环境变量 > .env 文件。"""
    if app_dir:
        s = load_settings(app_dir)
        if s["ai"].get("api_key"):
            return s["ai"]["api_key"]
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if env_key:
        return env_key
    return _load_key_from_envfile()


class AIFiller:
    """把自然语言描述解析成元器件字段。"""

    def __init__(self, api_key: str | None = None,
                 base_url: str | None = None,
                 model: str | None = None,
                 app_dir: str | None = None):
        # 优先用显式参数, 否则读用户配置
        s = load_settings(app_dir) if app_dir else json.loads(json.dumps(DEFAULT_SETTINGS))
        ai = s.get("ai", {})
        provider = ai.get("provider", "online")
        self.api_key = api_key or ai.get("api_key", "") or get_api_key(app_dir)
        self.base_url = (base_url or ai.get("base_url") or
                         os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_SETTINGS["ai"]["base_url"]))
        self.model = model or ai.get("model") or "deepseek-chat"
        if provider == "ollama":
            # 本地离线模型: 无需 key, base_url 默认 Ollama 的 OpenAI 兼容地址
            self.api_key = self.api_key or "ollama"
            self.base_url = (self.base_url or "http://localhost:11434/v1").rstrip("/")
            if not model and not ai.get("model"):
                self.model = "qwen2.5:7b"
            return
        if not self.api_key:
            raise ValueError(
                "未配置 AI 接口。请到「设置 → AI」填写 API Key "
                "(DeepSeek/智谱GLM 等兼容接口均可)，或切换到「本地离线 (Ollama)」模式。"
            )

    def parse(self, category: str, text: str, fields: list, subcat_list: list | None = None) -> dict:
        """把描述解析成 {字段key: 值}。

        fields 为 [(key, 中文标签), ...]
        subcat_list 为当前分类的子分类列表 (用于 AI 判断子分类)。
        返回的 dict 只含本分类字段。
        """
        labels = [label for _, label in fields]
        subcats_hint = ""
        if subcat_list:
            subcats_hint = (
                "\n子分类(从中选一个最匹配的填入 subcat 字段, 没有匹配的填空): "
                + json.dumps(subcat_list, ensure_ascii=False)
            )

        prompt = f"""你是电子元器件仓库管理员。把用户的元器件描述解析为结构化 JSON。

分类: {category}
可用字段(键名用英文 key): {json.dumps(labels, ensure_ascii=False)}
{subcats_hint}

用户描述: {text}

要求:
1. 只输出 JSON，不要多余文字。
2. 名称/型号提取具体型号(如 STM32F103C8T6、RC0805FR-0710KL)，没有型号时提取类别名。
   注意: 位号编号(如 C1、R2、L3、U5 这种 字母+数字)不是型号, 绝不要作为名称, 名称应填规格值(如 10uF、10kΩ)。
   电容: 名称只填容值(如 10uF、100nF), 耐压(如 50V、25V)和材质(如 X7R、X5R、C0G、电解、钽)必须放进 spec, 格式如 "50V X7R"。
3. 品牌、封装、数量、库位尽量提取，缺失的字段省略。
4. 所有电气参数(阻值/容值/耐压/精度/功率/频率/电流等)合并写入 spec 字段，
   保留原始写法(如 10K ±1% 50V X7R)。
5. 描述中类别明显不属于本分类时，在 note 字段注明"疑似分类:xx"。
6. 数量默认 10。"""

        messages = [{"role": "user", "content": prompt}]
        raw = self._chat(messages)
        data = self._parse_json(raw)

        # 只保留本分类字段 key（兼容 AI 返回中文标签或英文 key 两种情况）
        label_to_key = {label: k for k, label in fields}
        valid_keys = {k for k, _ in fields}
        result = {}
        for k, v in data.items():
            if k in valid_keys:
                key = k
            elif k in label_to_key:
                key = label_to_key[k]
            else:
                continue
            if v is not None:
                result[key] = str(v)
        # 字段顺序对齐
        ordered = {}
        for k, _ in fields:
            if k in result:
                ordered[k] = result[k]
        return ordered

    # ── 内部 ────────────────────────────────────────────
    def _chat(self, messages: list) -> str:
        url = chat_completions_url(self.base_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "messages": messages, "temperature": 0.1, "max_tokens": 1024}
        resp = httpx.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        # 去掉 markdown 代码围栏
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        # 找第一个 { 到最后一个 }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        return json.loads(text)
