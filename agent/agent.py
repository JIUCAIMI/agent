import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai_client import OpenAIQueryPlanner


Record = Dict[str, Any]


class SmartQueryAgent:
    def __init__(
        self,
        records: List[Record],
        planner: Optional[OpenAIQueryPlanner] = None,
    ):
        if not records:
            raise ValueError("数据为空，无法创建查询 agent。")
        self.records = records
        self.fields = list(records[0].keys())
        self.field_types = self._infer_field_types(records)
        self.string_value_index = self._build_string_value_index(records)
        self.planner = planner

    def ask(self, query: str) -> Dict[str, Any]:
        plan_source = "rules"
        plan = None

        if self.planner and self.planner.is_enabled:
            plan = self.planner.plan_query(
                query=query,
                fields=self.fields,
                field_types=self.field_types,
                sample_records=self.records[:5],
            )
            if plan:
                plan_source = "openai"

        if not plan:
            plan = self._build_plan(query)

        filtered = self._apply_filters(self.records, plan["filters"])
        raw_result = self._execute(filtered, plan)
        presentation = self._build_presentation(query, plan, filtered, raw_result, plan_source)
        return {
            "query": query,
            "plan": plan,
            "plan_source": plan_source,
            "matched_rows": len(filtered),
            "result": raw_result,
            "presentation": presentation,
        }

    def _build_plan(self, query: str) -> Dict[str, Any]:
        operation = self._detect_operation(query)
        metric_field = self._detect_metric_field(query, operation)
        group_field = self._detect_group_field(query)
        filters = self._extract_filters(query)
        return self._normalize_plan(
            {
                "operation": operation,
                "metric_field": metric_field,
                "group_field": group_field,
                "filters": filters,
            }
        )

    def _normalize_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        operation = plan.get("operation") or "list"
        if operation not in {"list", "count", "sum", "avg", "max", "min"}:
            operation = "list"

        metric_field = plan.get("metric_field")
        if metric_field not in self.fields:
            metric_field = None

        group_field = plan.get("group_field")
        if group_field not in self.fields:
            group_field = None

        filters = []
        for item in plan.get("filters", []):
            field = item.get("field")
            op = item.get("op")
            value = item.get("value")
            if field in self.fields and op in {"eq", "contains", "gt", "gte", "lt", "lte"} and value not in (None, ""):
                filters.append({"field": field, "op": op, "value": value})

        if operation == "list" and group_field and metric_field:
            operation = "sum" if self.field_types.get(metric_field) == "number" else "count"

        if operation in {"sum", "avg", "max", "min"} and not metric_field:
            metric_field = self._first_numeric_field()

        return {
            "operation": operation,
            "metric_field": metric_field,
            "group_field": group_field,
            "filters": filters,
        }

    def _execute(self, records: List[Record], plan: Dict[str, Any]) -> Any:
        operation = plan["operation"]
        metric_field = plan["metric_field"]
        group_field = plan["group_field"]

        if group_field:
            grouped: Dict[str, List[Record]] = defaultdict(list)
            for record in records:
                grouped[str(record.get(group_field, "未知"))].append(record)

            output = []
            for group_name, group_records in grouped.items():
                output.append(
                    {
                        "group": group_name,
                        "value": self._run_operation(group_records, operation, metric_field),
                        "rows": len(group_records),
                    }
                )

            return sorted(
                output,
                key=lambda item: item["value"] if isinstance(item["value"], (int, float)) else 0,
                reverse=True,
            )

        return self._run_operation(records, operation, metric_field)

    def _run_operation(self, records: List[Record], operation: str, metric_field: Optional[str]) -> Any:
        if operation == "list":
            return records[:10]
        if operation == "count":
            return len(records)

        numeric_values = self._numeric_values(records, metric_field)
        if not numeric_values:
            return {"message": "没有找到可用于计算的数值字段。", "field": metric_field}

        if operation == "sum":
            return round(sum(numeric_values), 2)
        if operation == "avg":
            return round(sum(numeric_values) / len(numeric_values), 2)
        if operation == "max":
            target = max(records, key=lambda item: self._safe_number(item.get(metric_field)) or float("-inf"))
            return {"value": self._safe_number(target.get(metric_field)), "record": target}
        if operation == "min":
            target = min(records, key=lambda item: self._safe_number(item.get(metric_field)) or float("inf"))
            return {"value": self._safe_number(target.get(metric_field)), "record": target}

        return records[:10]

    def _build_presentation(
        self,
        query: str,
        plan: Dict[str, Any],
        filtered: List[Record],
        raw_result: Any,
        plan_source: str,
    ) -> Dict[str, Any]:
        operation = plan["operation"]
        metric_field = plan["metric_field"]
        group_field = plan["group_field"]
        filters = plan["filters"]

        filter_text = "，".join(
            f"{item['field']} {self._op_label(item['op'])} {item['value']}"
            for item in filters
        ) or "无筛选条件"

        cards = [
            {"label": "匹配记录", "value": str(len(filtered))},
            {"label": "查询动作", "value": self._operation_label(operation)},
            {"label": "解析来源", "value": "OpenAI" if plan_source == "openai" else "本地规则"},
            {"label": "筛选条件", "value": filter_text},
        ]

        if metric_field:
            cards.append({"label": "指标字段", "value": metric_field})
        if group_field:
            cards.append({"label": "分组字段", "value": group_field})

        summary = self._build_summary(query, operation, metric_field, group_field, len(filtered), raw_result)
        table = self._build_table(raw_result)
        chart = self._build_chart(table, group_field, metric_field)
        suggestions = self._build_suggestions(operation, metric_field, group_field)

        return {
            "summary": summary,
            "cards": cards,
            "table": table,
            "chart": chart,
            "suggestions": suggestions,
        }

    def _build_summary(
        self,
        query: str,
        operation: str,
        metric_field: Optional[str],
        group_field: Optional[str],
        matched_rows: int,
        raw_result: Any,
    ) -> str:
        if matched_rows == 0:
            return f"没有找到符合“{query}”的记录。你可以换一个条件，或先查看可用字段。"

        if isinstance(raw_result, dict) and "message" in raw_result:
            return raw_result["message"]

        if operation == "count":
            return f"共找到 {raw_result} 条记录。"

        if operation == "sum":
            if group_field and isinstance(raw_result, list) and raw_result:
                top = raw_result[0]
                return f"已按{group_field}汇总{metric_field or '指标'}。当前最高的是{top['group']}，结果为{top['value']}。"
            return f"{metric_field or '指标'}的合计为 {raw_result}。"

        if operation == "avg":
            return f"{metric_field or '指标'}的平均值为 {raw_result}。"

        if operation in {"max", "min"} and isinstance(raw_result, dict):
            value = raw_result.get("value")
            record = raw_result.get("record", {})
            record_text = "，".join(f"{key}: {value}" for key, value in list(record.items())[:4])
            return f"{metric_field or '指标'}的{self._operation_label(operation)}结果为 {value}。对应记录：{record_text}。"

        if group_field and isinstance(raw_result, list):
            return f"已按{group_field}输出分组结果，共 {len(raw_result)} 组。"

        if isinstance(raw_result, list):
            return f"已返回 {min(len(raw_result), 10)} 条示例记录，共匹配 {matched_rows} 条。"

        return f"查询已完成，共匹配 {matched_rows} 条记录。"

    def _build_table(self, raw_result: Any) -> Dict[str, Any]:
        if isinstance(raw_result, list) and raw_result:
            return {"columns": list(raw_result[0].keys()), "rows": raw_result}

        if isinstance(raw_result, dict) and "record" in raw_result:
            record = raw_result["record"]
            return {"columns": list(record.keys()), "rows": [record]}

        if isinstance(raw_result, (int, float)):
            return {"columns": ["结果"], "rows": [{"结果": raw_result}]}

        if isinstance(raw_result, dict):
            return {"columns": list(raw_result.keys()), "rows": [raw_result]}

        return {"columns": [], "rows": []}

    def _build_chart(
        self,
        table: Dict[str, Any],
        group_field: Optional[str],
        metric_field: Optional[str],
    ) -> Dict[str, Any]:
        rows = table.get("rows", [])
        columns = table.get("columns", [])
        if not rows:
            return {"type": "none", "title": "", "labels": [], "values": []}

        if {"group", "value"}.issubset(columns):
            return {
                "type": "bar",
                "title": f"{group_field or '分组'} vs {metric_field or '值'}",
                "labels": [str(row.get("group", "")) for row in rows[:12]],
                "values": [self._safe_number(row.get("value")) or 0 for row in rows[:12]],
            }

        string_columns = [column for column in columns if any(isinstance(row.get(column), str) for row in rows)]
        number_columns = [
            column
            for column in columns
            if any(self._safe_number(row.get(column)) is not None for row in rows)
        ]

        if string_columns and number_columns:
            label_column = string_columns[0]
            value_column = number_columns[0]
            return {
                "type": "bar",
                "title": f"{label_column} vs {value_column}",
                "labels": [str(row.get(label_column, "")) for row in rows[:12]],
                "values": [self._safe_number(row.get(value_column)) or 0 for row in rows[:12]],
            }

        return {"type": "none", "title": "", "labels": [], "values": []}

    def _build_suggestions(
        self,
        operation: str,
        metric_field: Optional[str],
        group_field: Optional[str],
    ) -> List[str]:
        suggestions = []
        if metric_field and operation != "avg":
            suggestions.append(f"{metric_field}平均值是多少")
        if metric_field and not group_field:
            preferred_fields = ["地区", "状态", "销售", "产品"]
            ordered_fields = preferred_fields + [field for field in self.fields if field not in preferred_fields]
            for field in ordered_fields:
                if self.field_types.get(field) == "string" and not field.lower().endswith("id"):
                    suggestions.append(f"按{field}统计{metric_field}")
                    break
        if operation != "count":
            suggestions.append("有多少条记录")
        if len(suggestions) < 3:
            suggestions.append("显示前10条记录")
        return suggestions[:3]

    def _apply_filters(self, records: List[Record], filters: List[Dict[str, Any]]) -> List[Record]:
        output = records
        for item in filters:
            field = item["field"]
            op = item["op"]
            value = item["value"]
            next_output = []
            for record in output:
                current = record.get(field)
                if self._match_filter(current, op, value):
                    next_output.append(record)
            output = next_output
        return output

    def _match_filter(self, current: Any, op: str, value: Any) -> bool:
        if op == "eq":
            return str(current).lower() == str(value).lower()
        if op == "contains":
            return str(value).lower() in str(current).lower()

        current_number = self._safe_number(current)
        compare_number = self._safe_number(value)
        if current_number is None or compare_number is None:
            return False

        if op == "gt":
            return current_number > compare_number
        if op == "gte":
            return current_number >= compare_number
        if op == "lt":
            return current_number < compare_number
        if op == "lte":
            return current_number <= compare_number
        return False

    def _extract_filters(self, query: str) -> List[Dict[str, Any]]:
        filters: List[Dict[str, Any]] = []
        normalized = query.replace("＝", "=").replace("，", ",").replace("。", "")

        for field in self.fields:
            explicit_patterns = [
                (rf"{re.escape(field)}\s*(?:=|是|为|等于)\s*([^,，。]+?)(?:的|且|并且|$)", "eq"),
                (rf"{re.escape(field)}\s*包含\s*([^\s,，。]+)", "contains"),
                (rf"{re.escape(field)}\s*(?:大于|超过|高于)\s*(\d+(?:\.\d+)?)", "gt"),
                (rf"{re.escape(field)}\s*(?:不少于|不低于|大于等于)\s*(\d+(?:\.\d+)?)", "gte"),
                (rf"{re.escape(field)}\s*(?:小于|低于)\s*(\d+(?:\.\d+)?)", "lt"),
                (rf"{re.escape(field)}\s*(?:不超过|不高于|小于等于)\s*(\d+(?:\.\d+)?)", "lte"),
            ]
            for pattern, op in explicit_patterns:
                match = re.search(pattern, normalized, flags=re.IGNORECASE)
                if match:
                    raw_value = match.group(1).strip()
                    trimmed_value = re.sub(r"(订单|记录|数据|有多少条|是多少)$", "", raw_value).strip()
                    filters.append({"field": field, "op": op, "value": trimmed_value or raw_value})

        query_lower = normalized.lower()
        for field, values in self.string_value_index.items():
            for value in values:
                if len(str(value)) < 2:
                    continue
                if str(value).lower() in query_lower and not any(f["field"] == field for f in filters):
                    filters.append({"field": field, "op": "eq", "value": value})
                    break

        return filters

    def _detect_operation(self, query: str) -> str:
        q = query.lower()
        if any(keyword in q for keyword in ["平均", "均值", "avg", "average"]):
            return "avg"
        if any(keyword in q for keyword in ["总和", "合计", "汇总", "sum", "总计"]):
            return "sum"
        if any(keyword in q for keyword in ["最多", "最高", "最大", "top", "max"]):
            return "max"
        if any(keyword in q for keyword in ["最少", "最低", "最小", "min"]):
            return "min"
        if any(keyword in q for keyword in ["多少条", "几条", "数量", "count", "总数", "多少个"]):
            return "count"
        return "list"

    def _detect_metric_field(self, query: str, operation: str) -> Optional[str]:
        q = query.lower()
        numeric_fields = [field for field, kind in self.field_types.items() if kind == "number"]

        for field in numeric_fields:
            if field.lower() in q:
                return field

        metric_aliases = {
            "销售额": ["销售额", "金额", "成交额", "gmv", "revenue"],
            "数量": ["数量", "件数", "count", "qty"],
            "利润": ["利润", "profit"],
        }

        for field in numeric_fields:
            aliases = metric_aliases.get(field, [field])
            if any(alias.lower() in q for alias in aliases):
                return field

        if operation in {"sum", "avg", "max", "min"}:
            return self._first_numeric_field()
        return None

    def _detect_group_field(self, query: str) -> Optional[str]:
        for field in self.fields:
            if re.search(rf"(按|每个|各|分组).{{0,3}}{re.escape(field)}", query):
                return field
            if re.search(rf"{re.escape(field)}.{{0,3}}(分组|统计)", query):
                return field
        return None

    def _first_numeric_field(self) -> Optional[str]:
        for field, kind in self.field_types.items():
            if kind == "number":
                return field
        return None

    def _numeric_values(self, records: List[Record], field: Optional[str]) -> List[float]:
        if not field:
            return []
        output = []
        for record in records:
            number = self._safe_number(record.get(field))
            if number is not None:
                output.append(number)
        return output

    def _infer_field_types(self, records: List[Record]) -> Dict[str, str]:
        output: Dict[str, str] = {}
        for field in self.fields:
            sample_values = [record.get(field) for record in records[:20] if record.get(field) not in (None, "")]
            if sample_values and all(self._safe_number(value) is not None for value in sample_values):
                output[field] = "number"
            else:
                output[field] = "string"
        return output

    def _build_string_value_index(self, records: List[Record]) -> Dict[str, List[str]]:
        output: Dict[str, List[str]] = {}
        for field, kind in self.field_types.items():
            if kind != "string":
                continue
            values = []
            seen = set()
            for record in records[:200]:
                value = record.get(field)
                if value in (None, ""):
                    continue
                text = str(value)
                if text not in seen:
                    seen.add(text)
                    values.append(text)
            output[field] = values[:30]
        return output

    @staticmethod
    def _safe_number(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _op_label(op: str) -> str:
        return {
            "eq": "等于",
            "contains": "包含",
            "gt": "大于",
            "gte": "大于等于",
            "lt": "小于",
            "lte": "小于等于",
        }.get(op, op)

    @staticmethod
    def _operation_label(operation: str) -> str:
        return {
            "list": "查看明细",
            "count": "统计数量",
            "sum": "求和汇总",
            "avg": "计算平均值",
            "max": "最大值",
            "min": "最小值",
        }.get(operation, operation)


def load_records(data_path: str) -> List[Record]:
    path = Path(data_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到数据文件: {path}")

    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("JSON 数据必须是对象数组。")
        return data

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    raise ValueError("当前只支持 .json 和 .csv 文件。")


def main() -> None:
    parser = argparse.ArgumentParser(description="一个简单的智能查询数据 agent")
    parser.add_argument("--data", required=True, help="CSV 或 JSON 数据文件路径")
    parser.add_argument("--query", required=True, help="自然语言查询语句")
    parser.add_argument("--openai-model", default=None, help="可选，指定 OpenAI 模型")
    args = parser.parse_args()

    records = load_records(args.data)
    planner = OpenAIQueryPlanner(model=args.openai_model)
    agent = SmartQueryAgent(records, planner=planner)
    answer = agent.ask(args.query)
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
