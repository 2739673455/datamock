from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from curl_cffi.requests import Session
from scrapling import Selector

logger = logging.getLogger("finance_seed_crawler")
USER_AGENT = "Mozilla/5.0 finance-seed-research"
DEFAULT_REFERENCE_URLS = [
    "https://www.fisglobal.com/products/digital-one",
    "https://www.jackhenry.com/what-we-offer/digital-banking",
    "https://www.loanpro.io/",
    "https://www.abrigo.com/software/lending-and-credit-risk/",
    "https://newgensoft.com/solutions/industries/financial-institutions/lending-loan-origination/",
    "https://plaid.com/industries/consumer-lending/",
    "https://www.salesforce.com/financial-services/debt-collection-software/",
    "https://www.meridianlink.com/products/collect/",
]


@dataclass(frozen=True)
class CsvSpec:
    relative_path: str
    headers: list[str]
    rows: list[dict[str, Any]]


class FinanceSeedCrawler:
    def __init__(
        self,
        output_root: Path,
        *,
        delay_seconds: float,
        timeout_seconds: int,
        refresh_cache: bool,
        write_raw: bool,
    ) -> None:
        self.output_root = output_root
        self.seed_root = output_root / "seeds"
        self.raw_root = self.seed_root / "raw" / "reference_pages"
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.write_raw = write_raw
        self.http = Session(impersonate="chrome")
        self.last_request_at = 0.0

    def run(self, urls: list[str]) -> dict[str, int]:
        self.ensure_dirs()
        source_refs = [self.fetch_reference(url) for url in urls]
        if self.write_raw:
            self.write_json(self.raw_root / "source_references.json", source_refs)
            self.write_json(
                self.raw_root / "reference_terms.json",
                self.extract_reference_terms(source_refs),
            )
        csv_specs = self.build_seed_specs()
        for spec in csv_specs:
            self.write_csv(self.seed_root / spec.relative_path, spec.headers, spec.rows)
        return {
            "source_pages": len(source_refs),
            "csv_files": len(csv_specs),
            "csv_rows": sum(len(spec.rows) for spec in csv_specs),
        }

    def ensure_dirs(self) -> None:
        for relative_dir in [
            "1_foundation",
            "2_product",
            "3_rule",
        ]:
            (self.seed_root / relative_dir).mkdir(parents=True, exist_ok=True)
        if self.write_raw:
            self.raw_root.mkdir(parents=True, exist_ok=True)

    def fetch_reference(self, url: str) -> dict[str, Any]:
        self.wait()
        try:
            response = self.http.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout_seconds,
                verify=False,
            )
            status_code = response.status_code
            html = response.text if response.ok else ""
        except Exception as exc:
            logger.warning("fetch failed url=%s error=%s", url, exc)
            status_code = 0
            html = ""

        page = Selector(html) if html else None
        title = self.clean_text(page.css("title::text").get() or "") if page else ""
        headings = self.extract_texts(page, "h1::text, h2::text, h3::text") if page else []
        nav_items = self.extract_texts(page, "a::text, li::text") if page else []
        summary_terms = self.select_terms(headings + nav_items)
        return {
            "url": url,
            "domain": urlparse(url).netloc,
            "status_code": status_code,
            "title": title,
            "headings": headings[:40],
            "summary_terms": summary_terms[:80],
        }

    def wait(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self.last_request_at = time.monotonic()

    def extract_texts(self, page: Selector, selector: str) -> list[str]:
        values: list[str] = []
        for value in page.css(selector).getall():
            text = self.clean_text(re.sub(r"<[^>]+>", " ", str(value)))
            if text and text not in values:
                values.append(text)
        return values

    def select_terms(self, texts: list[str]) -> list[str]:
        keywords = [
            "account",
            "banking",
            "payment",
            "loan",
            "lending",
            "credit",
            "risk",
            "fraud",
            "aml",
            "collection",
            "deposit",
            "origination",
            "servicing",
            "business",
            "consumer",
            "digital",
            "open banking",
            "wealth",
            "portfolio",
        ]
        terms: list[str] = []
        for text in texts:
            lowered = text.lower()
            if any(keyword in lowered for keyword in keywords):
                terms.append(text)
        return terms

    def extract_reference_terms(
        self, source_refs: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        terms: dict[str, list[str]] = {
            "channel_terms": [],
            "account_terms": [],
            "loan_terms": [],
            "risk_terms": [],
            "collection_terms": [],
        }
        mapping = {
            "channel_terms": ["digital", "mobile", "online", "open banking", "branch"],
            "account_terms": ["account", "deposit", "payment", "transfer"],
            "loan_terms": ["loan", "lending", "origination", "servicing", "consumer"],
            "risk_terms": ["risk", "fraud", "aml", "credit"],
            "collection_terms": ["collection", "debt"],
        }
        for source in source_refs:
            for term in source.get("summary_terms", []):
                lowered = str(term).lower()
                for bucket, keywords in mapping.items():
                    if any(keyword in lowered for keyword in keywords):
                        if term not in terms[bucket]:
                            terms[bucket].append(term)
        return {key: value[:40] for key, value in terms.items()}

    def build_seed_specs(self) -> list[CsvSpec]:
        return [
            self.dim_branch_spec(),
            self.dim_channel_spec(),
            self.dim_currency_spec(),
            self.dim_risk_level_spec(),
            self.dim_employee_spec(),
            self.dim_product_category_spec(),
            self.account_product_spec(),
            self.service_product_spec(),
            self.loan_product_spec(),
            self.loan_product_eligibility_rule_spec(),
            self.loan_product_rate_tier_spec(),
            self.loan_product_required_material_spec(),
            self.wealth_product_spec(),
            self.wealth_settlement_rule_spec(),
            self.risk_rule_spec(),
            self.risk_strategy_spec(),
            self.risk_strategy_rule_rel_spec(),
            self.business_metric_dict_spec(),
        ]

    def dim_branch_spec(self) -> CsvSpec:
        headers = [
            "id",
            "parent_id",
            "branch_code",
            "branch_name",
            "branch_level",
            "province",
            "city",
            "address",
            "service_phone",
            "branch_status",
            "opened_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        rows = [
            self.row(headers, 0, "", "ALL", "全行汇总", "head_office", "", "", "", "95588", "active", "2010-01-01 00:00:00", "", "2010-01-01 00:00:00", "2026-01-01 00:00:00"),
            self.row(headers, 1, "", "HO001", "中州银行总行", "head_office", "上海市", "上海市", "浦东新区金融大道 88 号", "95588", "active", "2010-01-01 00:00:00", "", "2010-01-01 00:00:00", "2026-01-01 00:00:00"),
        ]
        branch_defs = [
            ("上海", "上海市", "上海市", "021"),
            ("北京", "北京市", "北京市", "010"),
            ("深圳", "广东省", "深圳市", "0755"),
            ("广州", "广东省", "广州市", "020"),
            ("杭州", "浙江省", "杭州市", "0571"),
            ("南京", "江苏省", "南京市", "025"),
            ("成都", "四川省", "成都市", "028"),
            ("武汉", "湖北省", "武汉市", "027"),
        ]
        sub_names = ["中心", "东区", "西区", "北区", "南区"]
        outlet_names = ["营业部", "社区网点", "企业服务中心"]
        row_id = 2
        sub_branch_ids: list[tuple[int, str, str, str, str]] = []
        for branch_index, (short_name, province, city, phone_prefix) in enumerate(branch_defs, start=1):
            branch_id = row_id
            rows.append(
                self.row(headers, branch_id, 1, f"BR{branch_index:03d}", f"{short_name}分行", "branch", province, city, f"{city}{short_name}金融中心 {branch_index} 号", f"{phone_prefix}-95588{branch_index:03d}", "active", f"201{branch_index + 1}-01-01 00:00:00", "", f"201{branch_index + 1}-01-01 00:00:00", "2026-01-01 00:00:00")
            )
            row_id += 1
            for sub_index, sub_name in enumerate(sub_names, start=1):
                sub_id = row_id
                sub_code_no = (branch_index - 1) * len(sub_names) + sub_index
                rows.append(
                    self.row(headers, sub_id, branch_id, f"SB{sub_code_no:03d}", f"{short_name}{sub_name}支行", "sub_branch", province, city, f"{city}{sub_name}路 {sub_code_no * 18} 号", f"{phone_prefix}-95589{sub_code_no:03d}", "active", "2015-01-01 00:00:00", "", "2015-01-01 00:00:00", "2026-01-01 00:00:00")
                )
                sub_branch_ids.append((sub_id, short_name, sub_name, province, city))
                row_id += 1
        outlet_no = 1
        for sub_id, short_name, sub_name, province, city in sub_branch_ids:
            for outlet_name in outlet_names:
                rows.append(
                    self.row(headers, row_id, sub_id, f"OT{outlet_no:03d}", f"{short_name}{sub_name}{outlet_name}", "outlet", province, city, f"{city}{sub_name}街 {outlet_no * 7} 号", f"400-88{outlet_no:04d}", "active", "2016-01-01 00:00:00", "", "2016-01-01 00:00:00", "2026-01-01 00:00:00")
                )
                row_id += 1
                outlet_no += 1
        return CsvSpec("1_foundation/dim_branch.csv", headers, rows)

    def dim_channel_spec(self) -> CsvSpec:
        headers = [
            "id",
            "channel_code",
            "channel_name",
            "channel_type",
            "channel_status",
            "yn",
            "created_at",
            "updated_at",
        ]
        data = [
            (0, "ALL", "全部渠道", "batch", "active", 1),
            (1, "MOBILE_BANK", "手机银行", "mobile_bank", "active", 1),
            (2, "ONLINE_BANK", "网上银行", "online_bank", "active", 1),
            (3, "COUNTER", "营业柜面", "counter", "active", 1),
            (4, "OPEN_API", "开放银行 API", "open_api", "active", 1),
            (5, "PARTNER_APP", "合作方渠道", "partner", "active", 1),
            (6, "BATCH_JOB", "批处理渠道", "batch", "active", 1),
        ]
        rows = [
            self.row(headers, *item, "2018-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("1_foundation/dim_channel.csv", headers, rows)

    def dim_currency_spec(self) -> CsvSpec:
        headers = [
            "id",
            "currency_code",
            "currency_name",
            "symbol",
            "precision_scale",
            "yn",
            "created_at",
            "updated_at",
        ]
        data = [
            (1, "CNY", "人民币", "¥", 2, 1),
            (2, "USD", "美元", "$", 2, 1),
            (3, "HKD", "港币", "HK$", 2, 1),
            (4, "EUR", "欧元", "€", 2, 1),
            (5, "GBP", "英镑", "£", 2, 1),
            (6, "JPY", "日元", "¥", 0, 1),
        ]
        rows = [
            self.row(headers, *item, "2018-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("1_foundation/dim_currency.csv", headers, rows)

    def dim_risk_level_spec(self) -> CsvSpec:
        headers = [
            "id",
            "risk_level_code",
            "risk_level_name",
            "risk_level_type",
            "risk_score_min",
            "risk_score_max",
            "sort_no",
            "yn",
            "created_at",
            "updated_at",
        ]
        names = {
            "customer": ["保守型", "稳健型", "平衡型", "成长型", "进取型"],
            "product": ["低风险", "中低风险", "中风险", "中高风险", "高风险"],
            "event": ["提示", "关注", "可疑", "高危", "阻断"],
        }
        rows: list[dict[str, Any]] = []
        row_id = 1
        for level_type, level_names in names.items():
            prefix = {"customer": "C", "product": "P", "event": "E"}[level_type]
            for index, name in enumerate(level_names, start=1):
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        f"{prefix}{index}",
                        name,
                        level_type,
                        (index - 1) * 20,
                        index * 20 - 1 if index < 5 else 100,
                        index,
                        1,
                        "2018-01-01 00:00:00",
                        "2026-01-01 00:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("1_foundation/dim_risk_level.csv", headers, rows)

    def dim_employee_spec(self) -> CsvSpec:
        headers = [
            "id",
            "employee_no",
            "employee_name",
            "branch_id",
            "employee_role",
            "mobile",
            "email",
            "employee_status",
            "joined_at",
            "resigned_at",
            "created_at",
            "updated_at",
        ]
        roles = [
            ("relationship_manager", "客户经理"),
            ("loan_approver", "信贷审批员"),
            ("risk_officer", "风控员"),
            ("collector", "催收员"),
            ("operator", "运营人员"),
            ("customer_service", "客服人员"),
        ]
        rows: list[dict[str, Any]] = []
        row_id = 1
        for branch_id in range(2, 170):
            for role, role_name in roles:
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        f"EMP{row_id:06d}",
                        f"{role_name}{row_id:02d}",
                        branch_id,
                        role,
                        f"139{row_id:08d}",
                        f"emp{row_id:06d}@finance.example",
                        "active",
                        "2020-01-01 00:00:00",
                        "",
                        "2020-01-01 00:00:00",
                        "2026-01-01 00:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("1_foundation/dim_employee.csv", headers, rows)

    def dim_product_category_spec(self) -> CsvSpec:
        headers = [
            "id",
            "parent_id",
            "category_code",
            "category_name",
            "category_type",
            "category_level",
            "sort_no",
            "yn",
            "created_at",
            "updated_at",
        ]
        data = [
            (1, "", "ACCOUNT", "账户产品", "account", 1, 1),
            (2, "", "LOAN", "贷款产品", "loan", 1, 2),
            (3, "", "WEALTH", "理财产品", "wealth", 1, 3),
            (4, "", "SERVICE", "服务产品", "service", 1, 4),
            (11, 1, "ACCOUNT_DEMAND", "活期结算账户", "account", 2, 1),
            (12, 1, "ACCOUNT_LOAN_REPAY", "贷款还款账户", "account", 2, 2),
            (13, 1, "ACCOUNT_WEALTH", "理财资金账户", "account", 2, 3),
            (21, 2, "LOAN_CONSUMER", "消费贷款", "loan", 2, 1),
            (22, 2, "LOAN_CASH", "现金贷款", "loan", 2, 2),
            (23, 2, "LOAN_INSTALLMENT", "分期贷款", "loan", 2, 3),
            (24, 2, "LOAN_BUSINESS", "经营贷款", "loan", 2, 4),
            (25, 2, "LOAN_MORTGAGE", "抵押贷款", "loan", 2, 5),
            (26, 2, "LOAN_GUARANTEE", "担保贷款", "loan", 2, 6),
            (31, 3, "WEALTH_CASH", "现金管理", "wealth", 2, 1),
            (32, 3, "WEALTH_FIXED", "固定收益", "wealth", 2, 2),
            (33, 3, "WEALTH_MIXED", "混合策略", "wealth", 2, 3),
            (34, 3, "WEALTH_EQUITY", "权益策略", "wealth", 2, 4),
            (35, 3, "WEALTH_STRUCTURED", "结构性存款", "wealth", 2, 5),
            (41, 4, "SERVICE_ACCOUNT", "账户服务", "service", 2, 1),
            (42, 4, "SERVICE_TRANSACTION", "交易服务", "service", 2, 2),
            (43, 4, "SERVICE_WEALTH", "理财服务", "service", 2, 3),
            (44, 4, "SERVICE_LOAN", "贷款服务", "service", 2, 4),
            (45, 4, "SERVICE_SUPPORT", "客服服务", "service", 2, 5),
        ]
        rows = [
            self.row(headers, *item, 1, "2018-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("1_foundation/dim_product_category.csv", headers, rows)

    def account_product_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_code",
            "product_name",
            "category_id",
            "currency_code",
            "account_type",
            "min_open_amount",
            "daily_transfer_limit",
            "daily_withdraw_limit",
            "annual_fee_amount",
            "product_status",
            "created_at",
            "updated_at",
        ]
        data = [
            (1, "ACC_DEMAND_CNY", "人民币活期结算账户", 11, "CNY", "demand_deposit", 0, 500000, 100000, 0),
            (2, "ACC_SETTLE_USD", "美元结算账户", 11, "USD", "settlement", 100, 100000, 20000, 10),
            (3, "ACC_SETTLE_HKD", "港币结算账户", 11, "HKD", "settlement", 100, 200000, 50000, 10),
            (4, "ACC_LOAN_REPAY_CNY", "贷款还款专用账户", 12, "CNY", "loan_repayment", 0, 300000, 50000, 0),
            (5, "ACC_WEALTH_CNY", "理财资金账户", 13, "CNY", "wealth_settlement", 0, 1000000, 100000, 0),
            (6, "ACC_PAYROLL_CNY", "工资代发账户", 11, "CNY", "settlement", 0, 800000, 100000, 0),
            (7, "ACC_BUSINESS_CNY", "企业结算账户", 11, "CNY", "settlement", 1000, 5000000, 300000, 0),
            (8, "ACC_MERCHANT_CNY", "商户收单结算账户", 11, "CNY", "settlement", 0, 3000000, 200000, 0),
            (9, "ACC_VIRTUAL_CNY", "线上虚拟结算账户", 11, "CNY", "demand_deposit", 0, 300000, 50000, 0),
            (10, "ACC_ESCROW_CNY", "担保支付监管账户", 11, "CNY", "settlement", 0, 10000000, 0, 0),
            (11, "ACC_WEALTH_USD", "美元理财资金账户", 13, "USD", "wealth_settlement", 100, 200000, 20000, 10),
            (12, "ACC_BUSINESS_USD", "美元企业结算账户", 11, "USD", "settlement", 1000, 500000, 50000, 20),
            (13, "ACC_SETTLE_EUR", "欧元结算账户", 11, "EUR", "settlement", 100, 100000, 20000, 10),
            (14, "ACC_SETTLE_GBP", "英镑结算账户", 11, "GBP", "settlement", 100, 100000, 20000, 10),
            (15, "ACC_SETTLE_JPY", "日元结算账户", 11, "JPY", "settlement", 10000, 10000000, 1000000, 1000),
            (16, "ACC_LOAN_REPAY_USD", "美元贷款还款账户", 12, "USD", "loan_repayment", 100, 100000, 20000, 10),
            (17, "ACC_API_SETTLE_CNY", "开放银行结算账户", 11, "CNY", "settlement", 0, 5000000, 300000, 0),
            (18, "ACC_CROSS_BORDER_CNY", "跨境结算账户", 11, "CNY", "settlement", 1000, 2000000, 100000, 20),
        ]
        rows = [
            self.row(headers, *item, "active", "2019-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("2_product/account_product.csv", headers, rows)

    def service_product_spec(self) -> CsvSpec:
        headers = [
            "id",
            "service_code",
            "service_name",
            "category_id",
            "currency_code",
            "service_type",
            "fee_amount",
            "service_status",
            "created_at",
            "updated_at",
        ]
        data = [
            (1, "SVC_ACCOUNT_BASIC", "基础账户服务", 41, "CNY", "account_service", 0),
            (2, "SVC_TRANSFER_FAST", "快速转账服务", 42, "CNY", "transaction_service", 2),
            (3, "SVC_WEALTH_ADVISORY", "理财顾问服务", 43, "CNY", "wealth_service", 20),
            (4, "SVC_LOAN_EXPRESS", "贷款快速处理服务", 44, "CNY", "loan_service", 50),
            (5, "SVC_SUPPORT_PRIORITY", "优先客服服务", 45, "CNY", "support_service", 10),
            (6, "SVC_SMS_NOTICE", "短信通知服务", 41, "CNY", "account_service", 1),
            (7, "SVC_ESTATEMENT", "电子对账单服务", 41, "CNY", "account_service", 0),
            (8, "SVC_CROSS_BANK_TRANSFER", "跨行转账服务", 42, "CNY", "transaction_service", 3),
            (9, "SVC_WEALTH_REPORT", "理财持仓报告服务", 43, "CNY", "wealth_service", 5),
            (10, "SVC_LOAN_REPAY_REMIND", "贷款还款提醒服务", 44, "CNY", "loan_service", 0),
            (11, "SVC_COLLECTION_NEGOTIATE", "协商还款服务", 45, "CNY", "support_service", 0),
            (12, "SVC_API_ENTERPRISE", "企业开放接口服务", 42, "CNY", "transaction_service", 100),
            (13, "SVC_CARD_LOSS_REPORT", "银行卡挂失服务", 41, "CNY", "account_service", 0),
            (14, "SVC_LIMIT_ADJUST", "账户限额调整服务", 41, "CNY", "account_service", 0),
            (15, "SVC_CROSS_BORDER_REMIT", "跨境汇款服务", 42, "CNY", "transaction_service", 30),
            (16, "SVC_WEALTH_RISK_REVIEW", "理财风险复核服务", 43, "CNY", "wealth_service", 0),
            (17, "SVC_LOAN_EXTENSION", "贷款展期服务", 44, "CNY", "loan_service", 20),
            (18, "SVC_AML_REVIEW", "反洗钱复核服务", 45, "CNY", "support_service", 0),
        ]
        rows = [
            self.row(headers, *item, "active", "2019-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("2_product/service_product.csv", headers, rows)

    def loan_product_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_code",
            "product_name",
            "category_id",
            "currency_code",
            "risk_level_id",
            "loan_type",
            "min_amount",
            "max_amount",
            "min_term_months",
            "max_term_months",
            "annual_interest_rate",
            "min_interest_rate",
            "max_interest_rate",
            "collateral_required_flag",
            "guarantee_required_flag",
            "post_registration_allowed_flag",
            "min_guarantee_ratio",
            "repayment_method",
            "product_status",
            "created_at",
            "updated_at",
        ]
        data = [
            (1, "LOAN_CONSUMER_STD", "标准消费信用贷", 21, "CNY", 7, "consumer", 3000, 300000, 3, 36, 0.072, 0.048, 0.108, 0, 0, 0, "", "equal_principal_interest"),
            (2, "LOAN_CONSUMER_PLUS", "优享消费信用贷", 21, "CNY", 7, "consumer", 10000, 500000, 6, 60, 0.068, 0.045, 0.098, 0, 0, 0, "", "equal_principal_interest"),
            (3, "LOAN_CONSUMER_PAYROLL", "薪享消费贷", 21, "CNY", 6, "consumer", 5000, 300000, 3, 48, 0.062, 0.039, 0.092, 0, 0, 0, "", "equal_principal"),
            (4, "LOAN_CONSUMER_GREEN", "绿色消费贷", 21, "CNY", 7, "consumer", 5000, 400000, 6, 60, 0.066, 0.042, 0.095, 0, 0, 0, "", "equal_principal_interest"),
            (5, "LOAN_CASH_FAST", "极速现金贷", 22, "CNY", 8, "cash", 1000, 80000, 1, 24, 0.108, 0.072, 0.18, 0, 0, 0, "", "equal_principal_interest"),
            (6, "LOAN_CASH_SMALL", "小额周转现金贷", 22, "CNY", 8, "cash", 500, 50000, 1, 18, 0.128, 0.088, 0.2, 0, 0, 0, "", "equal_principal_interest"),
            (7, "LOAN_CASH_SALARY", "工资客户现金贷", 22, "CNY", 7, "cash", 1000, 120000, 1, 36, 0.096, 0.065, 0.15, 0, 0, 0, "", "equal_principal_interest"),
            (8, "LOAN_CASH_DIGITAL", "线上现金贷", 22, "CNY", 8, "cash", 1000, 100000, 1, 24, 0.118, 0.078, 0.18, 0, 0, 0, "", "equal_principal_interest"),
            (9, "LOAN_INSTALLMENT_EASY", "大额分期贷", 23, "CNY", 8, "installment", 5000, 200000, 6, 48, 0.086, 0.052, 0.13, 0, 0, 0, "", "equal_principal"),
            (10, "LOAN_INSTALLMENT_AUTO", "汽车消费分期贷", 23, "CNY", 7, "installment", 30000, 800000, 12, 60, 0.058, 0.039, 0.09, 0, 0, 0, "", "equal_principal_interest"),
            (11, "LOAN_INSTALLMENT_HOME", "家装分期贷", 23, "CNY", 7, "installment", 10000, 500000, 6, 60, 0.065, 0.042, 0.098, 0, 0, 0, "", "equal_principal_interest"),
            (12, "LOAN_INSTALLMENT_EDU", "教育分期贷", 23, "CNY", 7, "installment", 3000, 200000, 3, 36, 0.072, 0.048, 0.108, 0, 0, 0, "", "equal_principal_interest"),
            (13, "LOAN_BUSINESS_WORKING", "小微经营周转贷", 24, "CNY", 8, "business", 50000, 2000000, 6, 60, 0.069, 0.045, 0.12, 0, 1, 0, 1.2, "interest_first"),
            (14, "LOAN_BUSINESS_TAX", "税票经营贷", 24, "CNY", 8, "business", 30000, 1500000, 6, 48, 0.074, 0.048, 0.13, 0, 1, 0, 1.1, "equal_principal_interest"),
            (15, "LOAN_BUSINESS_MERCHANT", "商户经营贷", 24, "CNY", 8, "business", 20000, 800000, 3, 36, 0.082, 0.052, 0.14, 0, 1, 0, 1.1, "equal_principal_interest"),
            (16, "LOAN_BUSINESS_SUPPLY", "供应链经营贷", 24, "CNY", 7, "business", 100000, 3000000, 6, 60, 0.064, 0.042, 0.105, 0, 1, 0, 1.2, "interest_first"),
            (17, "LOAN_MORTGAGE_HOME", "房产抵押经营贷", 25, "CNY", 7, "business", 100000, 5000000, 12, 120, 0.052, 0.039, 0.082, 1, 0, 1, "", "equal_principal_interest"),
            (18, "LOAN_MORTGAGE_SHOP", "商铺抵押贷", 25, "CNY", 7, "business", 200000, 8000000, 12, 120, 0.056, 0.041, 0.088, 1, 0, 1, "", "equal_principal"),
            (19, "LOAN_MORTGAGE_CAR", "车辆抵押贷", 25, "CNY", 8, "consumer", 30000, 800000, 6, 60, 0.078, 0.052, 0.12, 1, 0, 0, "", "equal_principal_interest"),
            (20, "LOAN_MORTGAGE_CERT", "存单质押贷", 25, "CNY", 6, "consumer", 10000, 2000000, 3, 60, 0.046, 0.032, 0.068, 1, 0, 1, "", "one_time"),
            (21, "LOAN_GUARANTEE_SME", "小微保证担保贷", 26, "CNY", 8, "business", 50000, 1000000, 6, 48, 0.078, 0.052, 0.14, 0, 1, 0, 1.1, "equal_principal_interest"),
            (22, "LOAN_GUARANTEE_PERSONAL", "个人保证担保贷", 26, "CNY", 8, "consumer", 10000, 300000, 6, 36, 0.088, 0.058, 0.145, 0, 1, 0, 1.0, "equal_principal_interest"),
            (23, "LOAN_GUARANTEE_POLICY", "保单保证贷", 26, "CNY", 7, "consumer", 10000, 500000, 6, 48, 0.075, 0.05, 0.12, 0, 1, 0, 1.0, "equal_principal"),
            (24, "LOAN_GUARANTEE_GROUP", "集团保证经营贷", 26, "CNY", 8, "business", 100000, 3000000, 6, 60, 0.071, 0.048, 0.12, 0, 1, 0, 1.2, "interest_first"),
            (25, "LOAN_CONSUMER_MEDICAL", "医疗消费信用贷", 21, "CNY", 7, "consumer", 3000, 200000, 3, 36, 0.069, 0.045, 0.105, 0, 0, 0, "", "equal_principal_interest"),
            (26, "LOAN_CONSUMER_TRAVEL", "文旅消费信用贷", 21, "CNY", 7, "consumer", 3000, 150000, 3, 24, 0.075, 0.05, 0.115, 0, 0, 0, "", "equal_principal_interest"),
            (27, "LOAN_CASH_MICRO", "微额循环现金贷", 22, "CNY", 8, "cash", 500, 30000, 1, 12, 0.132, 0.09, 0.22, 0, 0, 0, "", "equal_principal_interest"),
            (28, "LOAN_CASH_APP", "移动端备用金", 22, "CNY", 8, "cash", 500, 50000, 1, 18, 0.126, 0.082, 0.2, 0, 0, 0, "", "equal_principal_interest"),
            (29, "LOAN_INSTALLMENT_DIGITAL", "数码产品分期贷", 23, "CNY", 7, "installment", 1000, 80000, 3, 24, 0.078, 0.052, 0.12, 0, 0, 0, "", "equal_principal"),
            (30, "LOAN_INSTALLMENT_APPLIANCE", "家电消费分期贷", 23, "CNY", 7, "installment", 1000, 60000, 3, 24, 0.074, 0.048, 0.112, 0, 0, 0, "", "equal_principal_interest"),
            (31, "LOAN_BUSINESS_ECOM", "电商经营贷", 24, "CNY", 8, "business", 30000, 1200000, 3, 36, 0.079, 0.052, 0.13, 0, 1, 0, 1.1, "interest_first"),
            (32, "LOAN_BUSINESS_INVOICE", "发票经营贷", 24, "CNY", 8, "business", 50000, 2000000, 6, 48, 0.072, 0.046, 0.12, 0, 1, 0, 1.2, "equal_principal_interest"),
            (33, "LOAN_MORTGAGE_FACTORY", "厂房抵押经营贷", 25, "CNY", 7, "business", 500000, 10000000, 12, 120, 0.055, 0.04, 0.085, 1, 0, 1, "", "equal_principal"),
            (34, "LOAN_MORTGAGE_EQUIPMENT", "设备抵押经营贷", 25, "CNY", 8, "business", 100000, 5000000, 12, 84, 0.064, 0.046, 0.098, 1, 0, 1, "", "equal_principal_interest"),
            (35, "LOAN_GUARANTEE_SUPPLIER", "供应商保证贷", 26, "CNY", 8, "business", 50000, 1500000, 6, 48, 0.076, 0.05, 0.13, 0, 1, 0, 1.2, "interest_first"),
            (36, "LOAN_GUARANTEE_FAMILY", "家庭保证消费贷", 26, "CNY", 8, "consumer", 10000, 300000, 6, 36, 0.084, 0.056, 0.135, 0, 1, 0, 1.0, "equal_principal_interest"),
        ]
        rows = [
            self.row(headers, *item, "active", "2019-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("2_product/loan_product.csv", headers, rows)

    def loan_product_eligibility_rule_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_id",
            "rule_code",
            "rule_name",
            "rule_type",
            "rule_expression",
            "threshold_value",
            "decision_action",
            "yn",
            "created_at",
            "updated_at",
        ]
        base_rules = [
            ("CUSTOMER_TYPE", "客户类型准入", "customer_type", "customer_type in allowed_customer_types", "personal,enterprise", "reject"),
            ("MIN_INCOME", "最低收入准入", "income", "monthly_income_amount >= threshold", "5000", "manual_review"),
            ("MAX_DTI", "负债收入比准入", "debt_ratio", "debt_income_ratio <= threshold", "0.55", "manual_review"),
            ("MIN_CREDIT_SCORE", "征信评分准入", "credit_score", "credit_score >= threshold", "620", "reject"),
            ("BLACKLIST_BLOCK", "黑名单阻断", "blacklist", "blacklist_hit = 0", "0", "reject"),
            ("MATERIAL_REQUIRED", "材料完整性准入", "material", "required_material_valid = 1", "1", "supplement_material"),
        ]
        rows: list[dict[str, Any]] = []
        row_id = 1
        for product_id in range(1, 37):
            for code, name, rule_type, expression, threshold, action in base_rules:
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        product_id,
                        f"P{product_id}_{code}",
                        name,
                        rule_type,
                        expression,
                        threshold,
                        action,
                        1,
                        "2019-01-01 00:00:00",
                        "2026-01-01 00:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("2_product/loan_product_eligibility_rule.csv", headers, rows)

    def loan_product_rate_tier_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_id",
            "tier_code",
            "score_min",
            "score_max",
            "term_min_months",
            "term_max_months",
            "amount_min",
            "amount_max",
            "annual_interest_rate",
            "yn",
            "created_at",
            "updated_at",
        ]
        rows: list[dict[str, Any]] = []
        row_id = 1
        tiers = [
            ("A", 760, 1000, 1, 24, 0, 300000, 0.052),
            ("B", 680, 759, 1, 36, 0, 1000000, 0.078),
            ("C", 620, 679, 1, 60, 0, 5000000, 0.108),
        ]
        for product_id in range(1, 37):
            for tier in tiers:
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        product_id,
                        f"P{product_id}_{tier[0]}",
                        *tier[1:],
                        1,
                        "2019-01-01 00:00:00",
                        "2026-01-01 00:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("2_product/loan_product_rate_tier.csv", headers, rows)

    def loan_product_required_material_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_id",
            "material_type",
            "required_stage",
            "required_flag",
            "waivable_flag",
            "yn",
            "created_at",
            "updated_at",
        ]
        common = [
            ("identity", "application", 1, 0),
            ("income", "application", 1, 1),
            ("credit_authorization", "application", 1, 0),
            ("bank_statement", "approval", 1, 1),
        ]
        business_products = set(range(13, 17)) | {17, 18, 21, 24, 31, 32, 33, 34, 35}
        collateral_products = {17, 18, 19, 20, 33, 34}
        guarantee_products = {13, 14, 15, 16, 21, 22, 23, 24, 31, 32, 35, 36}
        rows: list[dict[str, Any]] = []
        row_id = 1
        for product_id in range(1, 37):
            items = list(common)
            if product_id in business_products:
                items.extend([
                    ("business_license", "application", 1, 0),
                    ("tax_record", "approval", 1, 1),
                ])
            if product_id in collateral_products:
                items.extend([
                    ("collateral_document", "approval", 1, 0),
                    ("collateral_contract", "contract", 1, 0),
                ])
            if product_id in guarantee_products:
                items.extend([
                    ("guarantee_document", "approval", 1, 0),
                    ("guarantee_contract", "contract", 1, 0),
                ])
            for item in items:
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        product_id,
                        *item,
                        1,
                        "2019-01-01 00:00:00",
                        "2026-01-01 00:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("2_product/loan_product_required_material.csv", headers, rows)

    def wealth_product_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_code",
            "product_name",
            "category_id",
            "currency_code",
            "risk_level_id",
            "product_type",
            "operation_mode",
            "min_purchase_amount",
            "increment_amount",
            "expected_yield_rate",
            "nav_based_flag",
            "sale_start_at",
            "sale_end_at",
            "value_date_rule",
            "redeem_rule",
            "product_status",
            "created_at",
            "updated_at",
        ]
        profiles = [
            ("CASH", "现金管理", 31, 6, "cash_management", "open", 1, 1, 0.018, 1, "T+1", "T+1到账"),
            ("FIXED90", "90天固定收益", 32, 7, "fixed_income", "closed", 10000, 1000, 0.032, 1, "T+1", "到期兑付"),
            ("FIXED180", "180天固定收益", 32, 7, "fixed_income", "closed", 10000, 1000, 0.036, 1, "T+1", "到期兑付"),
            ("MIXED", "平衡配置混合策略", 33, 8, "mixed", "periodic_open", 50000, 1000, 0.045, 1, "T+2", "每月开放赎回"),
            ("EQUITY", "权益成长优选", 34, 9, "equity", "periodic_open", 100000, 10000, 0.065, 1, "T+2", "每季开放赎回"),
            ("STRUCT", "指数挂钩结构性存款", 35, 8, "structured_deposit", "closed", 50000, 10000, 0.038, 0, "T+1", "到期兑付"),
        ]
        data = []
        for product_id in range(1, 121):
            code, name, category_id, risk_level_id, product_type, operation_mode, min_amount, increment_amount, yield_rate, nav_flag, value_rule, redeem_rule = profiles[(product_id - 1) % len(profiles)]
            term_no = (product_id - 1) // len(profiles) + 1
            data.append(
                (
                    product_id,
                    f"WM_{code}_{term_no:02d}",
                    f"中州{name}{term_no:02d}号",
                    category_id,
                    "CNY",
                    risk_level_id,
                    product_type,
                    operation_mode,
                    min_amount,
                    increment_amount,
                    round(yield_rate + term_no * 0.0003, 4),
                    nav_flag,
                    "2024-01-01 00:00:00",
                    "2026-12-31 23:59:59",
                    value_rule,
                    redeem_rule,
                    "selling",
                )
            )
        rows = [
            self.row(headers, *item, "2024-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("2_product/wealth_product.csv", headers, rows)

    def wealth_open_period_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_id",
            "period_no",
            "purchase_start_at",
            "purchase_end_at",
            "redeem_start_at",
            "redeem_end_at",
            "period_status",
            "created_at",
            "updated_at",
        ]
        rows: list[dict[str, Any]] = []
        row_id = 1
        open_product_ids = [
            product_id
            for product_id in range(1, 121)
            if (product_id - 1) % 6 in [0, 3, 4]
        ]
        for product_id in open_product_ids:
            for period_no, month in enumerate(["01", "04", "07", "10"], start=1):
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        product_id,
                        period_no,
                        f"2026-{month}-01 09:00:00",
                        f"2026-{month}-10 15:00:00",
                        f"2026-{month}-01 09:00:00",
                        f"2026-{month}-10 15:00:00",
                        "planned",
                        "2025-12-01 00:00:00",
                        "2025-12-01 00:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("2_product/wealth_open_period.csv", headers, rows)

    def wealth_trade_calendar_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_id",
            "calendar_date",
            "trade_flag",
            "purchase_confirm_date",
            "redeem_confirm_date",
            "redeem_arrival_date",
            "created_at",
        ]
        rows: list[dict[str, Any]] = []
        row_id = 1
        dates = [
            ("2026-01-02", 1, "2026-01-05", "2026-01-05", "2026-01-06"),
            ("2026-01-03", 0, "2026-01-05", "2026-01-05", "2026-01-06"),
            ("2026-01-05", 1, "2026-01-06", "2026-01-06", "2026-01-07"),
            ("2026-01-06", 1, "2026-01-07", "2026-01-07", "2026-01-08"),
            ("2026-01-07", 1, "2026-01-08", "2026-01-08", "2026-01-09"),
            ("2026-01-08", 1, "2026-01-09", "2026-01-09", "2026-01-12"),
            ("2026-01-09", 1, "2026-01-12", "2026-01-12", "2026-01-13"),
            ("2026-01-10", 0, "2026-01-12", "2026-01-12", "2026-01-13"),
            ("2026-01-12", 1, "2026-01-13", "2026-01-13", "2026-01-14"),
            ("2026-01-13", 1, "2026-01-14", "2026-01-14", "2026-01-15"),
        ]
        for product_id in range(1, 121):
            for item in dates:
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        product_id,
                        *item,
                        "2025-12-01 00:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("2_product/wealth_trade_calendar.csv", headers, rows)

    def wealth_settlement_rule_spec(self) -> CsvSpec:
        headers = [
            "id",
            "product_id",
            "purchase_confirm_days",
            "redeem_confirm_days",
            "redeem_arrival_days",
            "cutoff_time",
            "rule_status",
            "created_at",
            "updated_at",
        ]
        data = []
        for product_id in range(1, 121):
            profile_index = (product_id - 1) % 6
            if profile_index == 0:
                rule = (product_id, product_id, 1, 1, 1, "15:00:00")
            elif profile_index == 1:
                rule = (product_id, product_id, 1, 0, 90, "15:00:00")
            elif profile_index == 2:
                rule = (product_id, product_id, 1, 0, 180, "15:00:00")
            elif profile_index == 3:
                rule = (product_id, product_id, 2, 2, 3, "15:00:00")
            elif profile_index == 4:
                rule = (product_id, product_id, 2, 3, 5, "15:00:00")
            else:
                rule = (product_id, product_id, 1, 0, 180, "15:00:00")
            data.append(rule)
        rows = [
            self.row(headers, *item, "active", "2024-01-01 00:00:00", "2026-01-01 00:00:00")
            for item in data
        ]
        return CsvSpec("2_product/wealth_settlement_rule.csv", headers, rows)

    def wealth_product_notice_spec(self) -> CsvSpec:
        headers = [
            "id",
            "notice_no",
            "product_id",
            "notice_type",
            "notice_title",
            "notice_content",
            "published_at",
            "notice_status",
            "created_at",
            "updated_at",
        ]
        notice_types = [
            ("product_intro", "产品说明"),
            ("open_period", "开放期公告"),
            ("risk_tip", "风险提示"),
        ]
        rows: list[dict[str, Any]] = []
        row_id = 1
        for product_id in range(1, 121):
            for notice_type, notice_name in notice_types:
                rows.append(
                    self.row(
                        headers,
                        row_id,
                        f"NTC{row_id:08d}",
                        product_id,
                        notice_type,
                        f"中州理财产品{product_id:03d}{notice_name}",
                        f"本公告用于披露产品{product_id:03d}的{notice_name}信息",
                        "2026-01-01 09:00:00",
                        "published",
                        "2026-01-01 09:00:00",
                        "2026-01-01 09:00:00",
                    )
                )
                row_id += 1
        return CsvSpec("2_product/wealth_product_notice.csv", headers, rows)

    def risk_rule_spec(self) -> CsvSpec:
        headers = [
            "id",
            "rule_code",
            "rule_name",
            "rule_type",
            "risk_level_id",
            "rule_expression",
            "rule_version",
            "threshold_value",
            "decision_action",
            "rule_status",
            "created_at",
            "updated_at",
        ]
        data = [
            ("FRAUD_DEVICE_MULTI", "设备多账户登录", "fraud", 13, "device_account_count_24h > threshold", "3", "manual_review"),
            ("FRAUD_IP_GEO_JUMP", "异地登录跳变", "fraud", 13, "geo_distance_km_1h > threshold", "800", "manual_review"),
            ("AML_LARGE_TXN", "大额交易监控", "aml", 13, "transaction_amount >= threshold", "50000", "alert"),
            ("AML_STRUCTURING", "疑似拆分交易", "aml", 14, "small_txn_count_24h >= threshold", "5", "manual_review"),
            ("CREDIT_SCORE_LOW", "征信评分过低", "credit", 14, "credit_score < threshold", "620", "reject"),
            ("CREDIT_DTI_HIGH", "负债收入比过高", "credit", 13, "debt_income_ratio > threshold", "0.55", "manual_review"),
            ("TXN_AMOUNT_HIGH", "交易金额过高", "transaction", 13, "transaction_amount > threshold", "100000", "manual_review"),
            ("TXN_BLACKLIST_HIT", "黑名单交易命中", "transaction", 15, "blacklist_hit = 1", "1", "freeze"),
            ("WEALTH_RISK_MISMATCH", "理财风险不匹配", "wealth_suitability", 14, "customer_risk_sort < product_risk_sort", "1", "reject"),
            ("WEALTH_FIRST_HIGH_RISK", "首次购买高风险产品", "wealth_suitability", 13, "first_high_risk_purchase = 1", "1", "manual_review"),
            ("ACCOUNT_LOGIN_FAIL", "账户连续登录失败", "fraud", 12, "login_fail_count_1h >= threshold", "5", "manual_review"),
            ("ACCOUNT_DEVICE_NEW", "新设备高额交易", "fraud", 13, "new_device_txn_amount >= threshold", "20000", "manual_review"),
            ("AML_HIGH_RISK_REGION", "高风险地区交易", "aml", 14, "high_risk_region_hit = 1", "1", "alert"),
            ("CREDIT_OVERDUE_HISTORY", "历史逾期次数过多", "credit", 14, "overdue_count_12m > threshold", "3", "reject"),
            ("COLLECTION_BROKEN_PROMISE", "承诺还款违约", "collection", 13, "broken_promise_count >= threshold", "2", "manual_review"),
            ("COLLATERAL_VALUE_DROP", "抵押物估值下跌", "credit", 13, "collateral_ltv > threshold", "0.8", "manual_review"),
        ]
        rows = [
            self.row(
                headers,
                index,
                code,
                name,
                rule_type,
                risk_level_id,
                expression,
                "v1",
                threshold,
                action,
                "active",
                "2024-01-01 00:00:00",
                "2026-01-01 00:00:00",
            )
            for index, (code, name, rule_type, risk_level_id, expression, threshold, action) in enumerate(data, start=1)
        ]
        return CsvSpec("3_rule/risk_rule.csv", headers, rows)

    def risk_strategy_spec(self) -> CsvSpec:
        headers = [
            "id",
            "strategy_code",
            "strategy_name",
            "strategy_type",
            "applicable_event_type",
            "decision_mode",
            "strategy_version",
            "risk_level_id",
            "effective_from",
            "effective_to",
            "strategy_status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        data = [
            (1, "STR_FRAUD_TXN", "交易反欺诈策略", "fraud", "transaction", "highest_risk", "v1", 13, 3),
            (2, "STR_AML_TXN", "反洗钱交易监控策略", "aml", "suspicious_transaction", "score_sum", "v1", 13, 3),
            (3, "STR_CREDIT_LOAN", "贷款准入风控策略", "credit", "loan_application", "highest_risk", "v1", 13, 3),
            (4, "STR_TXN_MONITOR", "账户交易监控策略", "transaction", "transaction", "first_hit", "v1", 13, 5),
            (5, "STR_WEALTH_SUIT", "理财适当性策略", "wealth_suitability", "wealth_order", "first_hit", "v1", 12, 5),
            (6, "STR_COLLECTION_ASSIGN", "催收分案策略", "collection", "collection", "weighted_score", "v1", 13, 5),
            (7, "STR_ACCOUNT_SECURITY", "账户安全监控策略", "fraud", "account_login", "score_sum", "v1", 13, 3),
            (8, "STR_COLLATERAL_MONITOR", "抵押物风险监控策略", "credit", "collateral_asset", "highest_risk", "v1", 13, 3),
        ]
        rows = [
            self.row(
                headers,
                *item[:-1],
                "2024-01-01 00:00:00",
                "",
                "active",
                item[-1],
                "2024-01-01 00:00:00",
                "2026-01-01 00:00:00",
            )
            for item in data
        ]
        return CsvSpec("3_rule/risk_strategy.csv", headers, rows)

    def risk_strategy_rule_rel_spec(self) -> CsvSpec:
        headers = [
            "id",
            "strategy_id",
            "rule_id",
            "execute_order",
            "rule_weight",
            "required_flag",
            "stop_on_hit_flag",
            "decision_override",
            "yn",
            "created_at",
            "updated_at",
        ]
        mappings = [
            (1, 1, 1), (1, 2, 2), (1, 8, 3),
            (2, 3, 1), (2, 4, 2),
            (3, 5, 1), (3, 6, 2),
            (4, 7, 1), (4, 8, 2),
            (5, 9, 1), (5, 10, 2),
            (6, 6, 1), (6, 8, 2), (6, 15, 3),
            (7, 11, 1), (7, 12, 2),
            (8, 14, 1), (8, 16, 2),
        ]
        rows = [
            self.row(
                headers,
                index,
                strategy_id,
                rule_id,
                order,
                1,
                1 if order == 1 else 0,
                1 if rule_id in [5, 8, 9] else 0,
                "",
                1,
                "2024-01-01 00:00:00",
                "2026-01-01 00:00:00",
            )
            for index, (strategy_id, rule_id, order) in enumerate(mappings, start=1)
        ]
        return CsvSpec("3_rule/risk_strategy_rule_rel.csv", headers, rows)

    def business_metric_dict_spec(self) -> CsvSpec:
        headers = [
            "id",
            "metric_code",
            "metric_name",
            "stat_domain",
            "metric_type",
            "metric_unit",
            "currency_required_flag",
            "calculation_rule",
            "yn",
            "created_at",
            "updated_at",
        ]
        data = [
            ("CUSTOMER_ACTIVE_COUNT", "活跃客户数", "customer", "count", "户", 0, "count distinct active customer_id"),
            ("ACCOUNT_ACTIVE_COUNT", "正常账户数", "account", "count", "户", 0, "count active bank_account"),
            ("TRANSACTION_AMOUNT", "交易金额", "transaction", "amount", "元", 1, "sum success transaction_amount"),
            ("TRANSACTION_COUNT", "交易笔数", "transaction", "count", "笔", 0, "count success transaction"),
            ("WEALTH_AUM", "理财持仓规模", "wealth", "amount", "元", 1, "sum current_amount from wealth_position"),
            ("WEALTH_ORDER_AMOUNT", "理财订单金额", "wealth", "amount", "元", 1, "sum confirmed wealth_order amount"),
            ("LOAN_APPLICATION_COUNT", "贷款申请数", "loan", "count", "笔", 0, "count loan_application"),
            ("LOAN_DISBURSE_AMOUNT", "放款金额", "loan", "amount", "元", 1, "sum success loan_disbursement amount"),
            ("REPAYMENT_AMOUNT", "还款金额", "repayment", "amount", "元", 1, "sum success repayment_amount"),
            ("OVERDUE_AMOUNT", "逾期余额", "repayment", "amount", "元", 1, "sum active overdue outstanding_amount"),
            ("RISK_EVENT_COUNT", "风险事件数", "risk", "count", "件", 0, "count risk_event"),
            ("COLLECTION_RECOVERY_RATE", "催收回收率", "collection", "rate", "%", 0, "recovered_amount / assigned_amount"),
            ("CUSTOMER_NEW_COUNT", "新增客户数", "customer", "count", "户", 0, "count new customer_id"),
            ("ACCOUNT_NEW_COUNT", "新增账户数", "account", "count", "户", 0, "count new bank_account"),
            ("TRANSACTION_FAILED_COUNT", "失败交易笔数", "transaction", "count", "笔", 0, "count failed transaction"),
            ("WEALTH_POSITION_COUNT", "理财持仓数", "wealth", "count", "笔", 0, "count active wealth_position"),
            ("LOAN_CONTRACT_ACTIVE_COUNT", "有效贷款合同数", "loan", "count", "笔", 0, "count active loan_contract"),
            ("LOAN_OUTSTANDING_AMOUNT", "贷款余额", "loan", "amount", "元", 1, "sum outstanding principal"),
            ("OVERDUE_CONTRACT_COUNT", "逾期合同数", "repayment", "count", "笔", 0, "count overdue loan_contract"),
            ("RISK_MANUAL_REVIEW_COUNT", "人工复核任务数", "risk", "count", "件", 0, "count manual_review_task"),
            ("COLLECTION_CASE_COUNT", "催收案件数", "collection", "count", "件", 0, "count collection_case"),
            ("COLLECTION_RECOVERED_AMOUNT", "催收回收金额", "collection", "amount", "元", 1, "sum collection recovered amount"),
        ]
        rows = [
            self.row(
                headers,
                index,
                *item,
                1,
                "2024-01-01 00:00:00",
                "2026-01-01 00:00:00",
            )
            for index, item in enumerate(data, start=1)
        ]
        return CsvSpec("3_rule/business_metric_dict.csv", headers, rows)

    def write_csv(self, path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def row(self, headers: list[str], *values: Any) -> dict[str, Any]:
        if len(headers) != len(values):
            raise ValueError(f"row value count mismatch: {headers}")
        return {header: value for header, value in zip(headers, values)}

    def clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="../finance-data")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--write-raw", action="store_true")
    parser.add_argument("--url", action="append", dest="urls")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    urls = args.urls or DEFAULT_REFERENCE_URLS
    crawler = FinanceSeedCrawler(
        output_root,
        delay_seconds=args.delay,
        timeout_seconds=args.timeout,
        refresh_cache=args.refresh_cache,
        write_raw=args.write_raw,
    )
    summary = crawler.run(urls)
    logger.info("done: %s", summary)


if __name__ == "__main__":
    main()
