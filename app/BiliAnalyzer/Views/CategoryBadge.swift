import SwiftUI

struct CategoryBadge: View {
    let category: String

    private var display: String {
        switch category {
        case "entertainment": return "娱乐"
        case "tutorial": return "教程"
        case "knowledge": return "知识讲解"
        default: return category
        }
    }

    private var color: Color {
        switch category {
        case "entertainment": return .orange
        case "tutorial": return .green
        case "knowledge": return .blue
        default: return .gray
        }
    }

    var body: some View {
        Text(display)
            .font(.caption2)
            .fontWeight(.medium)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundColor(color)
            .clipShape(Capsule())
    }
}
