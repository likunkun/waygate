from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RequirementsRevisionIssue:
    code: str
    stage: str
    message: str


_STAGE_PRIORITY = {
    'scope': 0,
    'product_design': 1,
    'architecture': 2,
    'test_strategy': 3,
}


def classify_requirements_revision_reason(reason: str) -> list[RequirementsRevisionIssue]:
    text = _normalized_text(reason)
    compact = _compact_text(reason)
    issues: list[RequirementsRevisionIssue] = []

    _append_scope_issues(issues, text, compact)
    _append_product_design_issues(issues, text, compact)
    _append_architecture_issues(issues, text, compact)
    _append_test_strategy_issues(issues, text, compact)

    return issues


def select_requirements_revision_stage(reason: str) -> str:
    issues = classify_requirements_revision_reason(reason)
    if not issues:
        return 'scope'
    return _primary_issue(issues).stage


def requirements_auto_revision_semantic_key(reason: str) -> str:
    issues = classify_requirements_revision_reason(reason)
    if issues:
        issue = _primary_issue(issues)
        return f'{issue.stage}:{issue.code}'
    return 'generic:' + _normalized_text(reason)


def _append_scope_issues(
    issues: list[RequirementsRevisionIssue],
    text: str,
    compact: str,
) -> None:
    if _has_any(compact, (
        'missingacceptanceobligationrequirementsmapping',
        'missingacceptanceobligationcoverage',
        'acceptanceobligationrequirementsmapping',
        'acceptanceobligationmapping',
        'aomapping',
        'missingaotraceability',
        'ao映射',
        '验收义务映射',
    )):
        _append_issue(issues, 'scope', 'ao_mapping', 'Acceptance Obligation mapping is missing')

    if _is_e2e_scope_mapping_gap(text, compact):
        _append_issue(issues, 'scope', 'e2e_mapping', 'E2E review is not mapped to an E2E AC or active Journey')

    if _has_any(compact, (
        'unknownacceptancecriteria',
        'unknownacceptancecriterion',
        'unknownac',
        'unknownacs',
        '未知ac',
        '未知验收标准',
        '未知验收准则',
    )):
        _append_issue(issues, 'scope', 'unknown_acceptance_criteria', 'Unknown acceptance criteria reference')

    if _has_any(compact, (
        'unknownjourney',
        'unknownjourneys',
        '未知journey',
        '未知旅程',
    )):
        _append_issue(issues, 'scope', 'unknown_journey', 'Unknown Journey reference')

    if _has_any(compact, (
        'requirementssurfaceclassification',
        'surfaceclassification',
        'currentunitneedsuidesignfalse',
        'currentunitiswebsystemfalse',
        'falseuiflag',
        '产品表面分类',
        'ui分类',
    )):
        _append_issue(issues, 'scope', 'surface_classification', 'Requirements surface classification is inconsistent')

    if _has_any(compact, (
        'journeycontractrequired',
        'journeyacceptancematrixwithactivejourneyrows',
        'activejourneyrows',
        '旅程合同必需',
        '旅程契约必需',
        '缺少activejourney',
        '缺少活跃旅程',
    )):
        _append_issue(issues, 'scope', 'journey_contract_required', 'Journey contract requires active Journey rows')

    if _has_any(compact, (
        'accontractchange',
        'acceptancecriteriacontractchange',
        'journeycontractchange',
        'acjourneycontractchange',
        'contractchange',
        '验收标准合同变更',
        '验收准则合同变更',
        '旅程合同变更',
        '需求合同变更',
    )):
        _append_issue(issues, 'scope', 'contract_change', 'AC or Journey contract change requires Scope revision')


def _append_product_design_issues(
    issues: list[RequirementsRevisionIssue],
    text: str,
    compact: str,
) -> None:
    if _has_any(compact, (
        'prototypemanifestisrequired',
        'missingprototypemanifest',
        'requiresavalidprototypemanifest',
        'validprototypemanifest',
        'prototypemanifestnotfound',
        'prototypemanifestjsonisinvalid',
        'prototypemanifestmustcontain',
        'prototype-manifestjson',
        '原型manifest',
        '原型清单',
    )):
        _append_issue(issues, 'product_design', 'prototype_manifest', 'Prototype manifest is missing or invalid')

    if _has_any(compact, (
        'surfacecontracts',
        'surfacecontract',
        'uisurfaces',
        'pagestatetargets',
        'implementationtargets',
        'productiontargets',
        'realtargets',
        '表面契约',
        '实现目标',
    )):
        _append_issue(issues, 'product_design', 'prototype_surface_contract', 'Prototype surface contracts are incomplete')

    if _has_any(compact, (
        'pagestates',
        'clickpath',
        'accessmethod',
        'prototypepath',
        'prototypelocalfile',
        'pathdoesnotexist',
        'filenotfound',
        '页面状态',
        '点击路径',
        '访问方式',
    )):
        _append_issue(issues, 'product_design', 'prototype_review_details', 'Prototype review details are incomplete')

    if _has_any(compact, (
        '产品原型',
        '原型呢',
        '没有ui',
        '无ui',
        '怎么看',
        '产品设计',
        'productdesign',
        'ux',
        '页面',
        '详情页',
        '控制台',
    )) or 'prototype' in text:
        _append_issue(issues, 'product_design', 'product_experience', 'Product experience or prototype feedback')


def _append_architecture_issues(
    issues: list[RequirementsRevisionIssue],
    text: str,
    compact: str,
) -> None:
    test_quality_context = _has_test_strategy_quality_marker(text, compact)
    if _has_any(compact, (
        '架构交互',
        '交互架构',
        'technicalarchitecture',
        'architecture',
        '数据流',
        '状态写入',
        '外部系统',
        '模块边界',
        '运行时交互',
        '系统交互',
    )):
        _append_issue(issues, 'architecture', 'system_interaction', 'System interaction architecture is incomplete')

    if not test_quality_context and _has_any(compact, (
        'api',
        '接口',
        'dataflow',
        'statewrite',
        'externalsystem',
        'moduleboundary',
        'runtimeinteraction',
    )):
        _append_issue(issues, 'architecture', 'technical_boundary', 'Technical boundary or API/data flow is incomplete')


def _append_test_strategy_issues(
    issues: list[RequirementsRevisionIssue],
    text: str,
    compact: str,
) -> None:
    if _has_any(compact, (
        'mockpolicy',
        'environmentkind',
        'e2emethod',
        'expectedassertions',
        'fixture',
        'verificationlayer',
        'verificationlevel',
        'verificationlayer',
        '46matrix',
        'e2etestmethod',
        '测试策略',
        '验证层级',
        '证据形态',
        '断言',
        '夹具',
        '测试方法',
        '环境类型',
    )):
        _append_issue(issues, 'test_strategy', 'test_method_quality', 'Test method quality is incomplete')
        return

    if 'e2e' in compact and not _is_e2e_scope_mapping_gap(text, compact):
        _append_issue(issues, 'test_strategy', 'e2e_strategy', 'E2E test strategy needs revision')


def _is_e2e_scope_mapping_gap(text: str, compact: str) -> bool:
    if 'e2e' not in compact:
        return False
    has_mapping_language = (
        'map' in text
        or 'mapped' in text
        or 'mapping' in text
        or '映射' in compact
    )
    if not has_mapping_language:
        return False
    has_e2e_ac_or_journey = _has_any(compact, (
        'e2eac',
        'activee2ejourney',
        'activejourney',
        'acjourney',
        'journeyorac',
        'journey或ac',
        '旅程ac',
    ))
    has_negative_mapping = _has_any(compact, (
        'doesnotmap',
        'doesnotmapitto',
        'notmapped',
        'notmap',
        'missing',
        '缺少',
        '未映射',
        '没有映射',
    ))
    return has_e2e_ac_or_journey and has_negative_mapping


def _has_test_strategy_quality_marker(text: str, compact: str) -> bool:
    return _has_any(compact, (
        'mockpolicy',
        'environmentkind',
        'e2emethod',
        'expectedassertions',
        'fixture',
        'verificationlayer',
        'coreapistub',
        'coreapimock',
        '组件mock',
        '测试策略',
        '断言',
    )) or 'mock policy' in text


def _append_issue(
    issues: list[RequirementsRevisionIssue],
    stage: str,
    code: str,
    message: str,
) -> None:
    if any(issue.code == code for issue in issues):
        return
    issues.append(RequirementsRevisionIssue(code=code, stage=stage, message=message))


def _primary_issue(issues: list[RequirementsRevisionIssue]) -> RequirementsRevisionIssue:
    return sorted(issues, key=lambda issue: (_STAGE_PRIORITY[issue.stage], issue.code))[0]


def _normalized_text(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _compact_text(value: str) -> str:
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', _normalized_text(value))


def _has_any(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)
