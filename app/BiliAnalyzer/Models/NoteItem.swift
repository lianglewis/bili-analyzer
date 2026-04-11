import Foundation

/// 列表项 — 对应 GET /api/notes 返回的每一行
struct NoteItem: Codable, Identifiable, Hashable {
    let bvid: String
    let video_title: String
    let video_url: String
    let cover_url: String
    let category: String
    let created_at: String
    let updated_at: String

    var id: String { bvid }

    var categoryDisplay: String {
        switch category {
        case "entertainment": return "娱乐"
        case "tutorial": return "教程"
        case "knowledge": return "知识讲解"
        default: return category
        }
    }
}
