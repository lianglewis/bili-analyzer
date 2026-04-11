import SwiftUI

struct NoteCardView: View {
    let note: NoteItem

    var body: some View {
        HStack(spacing: 12) {
            CoverImageView(urlString: note.cover_url)

            VStack(alignment: .leading, spacing: 4) {
                Text(note.video_title)
                    .font(.system(size: 13, weight: .medium))
                    .lineLimit(2)
                    .foregroundColor(.primary)

                HStack(spacing: 6) {
                    CategoryBadge(category: note.category)
                    Text(note.updated_at.prefix(10))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }
}
