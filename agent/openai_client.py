import json
import os
from typing import Any, Dict, List, Optional
from urllib import error, request


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": ["list", "count", "sum", "avg", "max", "min"],
        },
        "metric_field": {
            "type": ["string", "null"],
        },
        "group_field": {
            "type": ["string", "null"],
        },
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "op": {
                        "type": "string",
                        "enum": ["eq", "contains", "gt", "gte", "lt", "lte"],
                    },
                    "value": {
                        "type": ["string", "number"],
                    },
                },
                "required": ["field", "op", "value"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["operation", "metric_field", "group_field", "filters"],
    "additionalProperties": False,
}


class OpenAIQueryPlanner:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5-mini")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com")).rstrip("/")

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def plan_query(
        self,
        query: str,
        fields: List[str],
        field_types: Dict[str, str],
        sample_records: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled:
            return None

        system_prompt = (
            "你是一个数据查询规划器。"
            "你的任务不是回答用户，而是把自然语言问题转换成查询计划 JSON。"
            "只允许使用给定字段名。"
            "如果不确定指标字段，就返回 null，不要编造字段。"
            "如果问题是分组统计，尽量识别 group_field。"
        )

        user_prompt = {
            "query": query,
            "fields": fields,
            "field_types": field_types,
            "sample_records": sample_records,
        }

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "query_plan",
                    "schema": PLAN_SCHEMA,
                    "strict": True,
                }
            },
        }

        req = request.Request(
            url=f"{self.base_url}/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
        except (error.URLError, error.HTTPError, TimeoutError, OSError):
            return None

        try:
            parsed = json.loads(body)
            content = self._extract_output_text(parsed)
            if not content:
                return None
            return json.loads(content)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def _extract_output_text(self, payload: Dict[str, Any]) -> Optional[str]:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]

        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        return None
