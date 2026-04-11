import Foundation

/// HTTP 客户端 — 只做三件事：列表、详情、删除
actor APIService {
    static let shared = APIService()

    private let base = "http://127.0.0.1:8765"

    func fetchNotes() async throws -> [NoteItem] {
        let url = URL(string: "\(base)/api/notes")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode([NoteItem].self, from: data)
    }

    func fetchNote(bvid: String) async throws -> AnalysisResult {
        let url = URL(string: "\(base)/api/notes/\(bvid)")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(AnalysisResult.self, from: data)
    }

    func deleteNote(bvid: String) async throws {
        let url = URL(string: "\(base)/api/notes/\(bvid)")!
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        let _ = try await URLSession.shared.data(for: req)
    }

    /// 获取笔记的原始 JSON 字符串（给 WKWebView 用）
    func fetchNoteJSON(bvid: String) async throws -> String {
        let url = URL(string: "\(base)/api/notes/\(bvid)")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return String(data: data, encoding: .utf8) ?? "{}"
    }
}
