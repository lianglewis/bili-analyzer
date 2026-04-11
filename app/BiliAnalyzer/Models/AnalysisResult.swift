import Foundation

/// 完整分析结果 — 对应 GET /api/notes/{bvid} 返回的 JSON
/// 只需要 Decodable 即可，不需要修改后写回
struct AnalysisResult: Codable {
    let video_title: String
    let video_url: String
    let bvid: String
    let cover_url: String?
    let category: String
    let summary: String
    let title_hook: String?
    let title_explanation: String?
    let practical_values: [PracticalValue]?
    let concept_flow: [FlowNode]?
    let term_groups: [TermGroup]?
    let qa_sections: [QASection]?
    let markdown: String?
}

struct PracticalValue: Codable {
    let point: String
    let detail: String
}

struct FlowNode: Codable {
    let label: String
    let timestamp: Double
    let depth: Int?
}

struct TermGroup: Codable {
    let group_name: String
    let terms: [KeyTerm]
}

struct KeyTerm: Codable {
    let term: String
    let timestamp: Double
    let explanation: String
}

struct QASection: Codable {
    let question: String
    let answer: String
    let timestamp: Double
    let quote: String?
    let sub_points: [String]?
    let evidence: String?
}
