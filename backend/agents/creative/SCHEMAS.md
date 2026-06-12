# Schema JSON dùng chung — đề xuất từ nhánh Creative [B]

> Bản đề xuất để chốt với Kiệt (Orchestrator + [A] Scout) và dùng chung cho [C] Producer, [E] Analyst.
> Nguyên tắc: mọi data truyền giữa agent là JSON thuần, tool không bao giờ raise — lỗi trả `{"status": "failed", "error": "..."}`.

## 1. `trend_digest` — [A] Scout → [B] Creative (nhịp tuần)

```json
{
  "week": "2026-W24",
  "niche": "đời sống công sở tech / employer branding",
  "trends": [
    {
      "id": "tr_001",
      "name": "Office tour POV",
      "format": "POV quay dọc, cắt nhanh 1-2s/cảnh",
      "hook_pattern": "Câu hỏi gây tò mò ngay giây đầu (ví dụ: 'Công ty gì mà có cả hồ bơi?')",
      "why_viral": "Thoả mãn tò mò về môi trường làm việc big tech",
      "example_ref": "https://tiktok.com/...",
      "fit_score": 0.9
    }
  ],
  "benchmarks": {
    "retention_3s": 0.65,
    "avg_views": 5000,
    "avg_like_rate": 0.04
  }
}
```

`benchmarks` đồng thời là seed ngưỡng tuyệt đối cho [E].

## 2. `insight_digest` — [E] Analyst → [B] Creative (nhịp ngày)

```json
{
  "date": "2026-06-11",
  "videos_analyzed": 6,
  "winning": [
    {"dimension": "hook", "insight": "Hook dạng câu hỏi trực tiếp giữ retention 3s tốt hơn hook kể chuyện (+18%)"},
    {"dimension": "topic", "insight": "Pillar 'canteen/đồ ăn' đang vượt benchmark view 2x"},
    {"dimension": "clip", "insight": "clip_007 (canteen giờ trưa) xuất hiện trong cả 2 video top"}
  ],
  "losing": [
    {"dimension": "length", "insight": "Video >52s rớt retention mạnh ở giây 35"}
  ],
  "recommendations": [
    "Ưu tiên hook câu hỏi + chủ đề ăn uống/đời sống, giữ video <=50s"
  ]
}
```

## 3. Kho clip — Drive `VNG_Insider_Footage/` + `00_INDEX.xlsx` (Nghi own)

Nguồn match chính là **cột `clip_tag` trong `00_INDEX.xlsx`** (file, clip_tag, do_dai_giay, ghi_chu) — KHÔNG match theo tên thư mục. 9 clip_tag: `campusngoaicanh` `khonggianmo` `gym` `canteencafe` `goclamviec` `cayxanhthugian` `hopteam` `buzones` `sukienclb`.

- [B] gán shot list theo **clip_tag** (+ `scene_hint` gợi ý cảnh cụ thể); bảng tag + ngân sách giây đã bake trong `prompts.CLIP_TAGS`.
- [C] Producer đọc `00_INDEX.xlsx` → chọn file cụ thể trong tag theo `scene_hint`/độ dài. Tag 1 clip (gym 6s, sukienclb 4s, hopteam 3s) chỉ nhận câu ngắn; câu dài phải có `alt_tag`; [C] mượn tag lân cận/freeze nếu vẫn thiếu.
- Xem `clips.sample.json` cho format INDEX dạng JSON (nếu [C] muốn convert từ xlsx).

## 4. `idea` — output của tool `generate_ideas`

```json
{
  "id": "idea_001",
  "title": "Canteen VNG có gì mà Starter nào cũng xuống đúng 11h30?",
  "pillar": "campus",
  "angle": "Tour canteen theo kiểu review đồ ăn, lồng giá trị 'công ty lo bữa trưa'",
  "trend_ref": "tr_001",
  "insight_ref": "Pillar canteen đang vượt benchmark 2x",
  "est_fit": 0.85
}
```

`pillar` ∈ `campus` (không gian & tiện ích) | `tuyendung` (cách vào VNG) | `bu` (các BU).

## 5. `script_package` — output của tool `generate_script` → [C] Producer + [D] Publisher

```json
{
  "idea": { "...": "idea object ở trên" },
  "text_hook": "Công ty gì mà tan ca xong còn lười về nhà?",
  "script": "Công ty gì mà tan ca xong còn lười về nhà? Đây, VNG Campus. Có phòng gym để xả hơi sau giờ làm. (...)",
  "shot_list": [
    {"line": 1, "voiceover": "Công ty gì mà tan ca xong còn lười về nhà? Đây, VNG Campus.", "duration_sec": 5, "clip_tag": "campusngoaicanh", "alt_tag": null, "scene_hint": "cổng chính"}
  ],
  "caption": "Tan ca mà chân không chịu ra cổng. Lưu lại nếu định nộp CV VNG nha.",
  "hashtags": ["#VNG", "#VNGCampus", "#Starter", "#congso"]
}
```

Hợp đồng với [C] Producer (đã chốt với Nam — owner [C]):
- `script` = **nguyên văn lời thoại liền mạch (1 string)** — Producer tự phân line/duration/voice, đưa thẳng vào TTS.
- KHÔNG có `total_duration_sec`. [B] vẫn validate nội bộ tổng 40-55s + thoại 110-140 từ trước khi trả (xem `warnings`).
- `shot_list` = mapping câu→`clip_tag` (9 nhóm trong `00_INDEX.xlsx`) + `scene_hint` + `alt_tag` dự phòng — field phụ, [C] dùng nếu cần, [E] cần để biết clip nào thắng.
- `text_hook` = chữ overlay 2-3 giây đầu video.

Hợp đồng với [D] Publisher: `caption` đưa thẳng vào `publish_video(video_path, caption)`.

## 6. Envelope lỗi (mọi tool, mọi agent)

```json
{"status": "ok | failed", "error": null, "data": {}}
```