"""Data mock cho workflow run ở mode mock — chạy offline, không tốn quota MaaS/ElevenLabs.

Nội dung theo brand guide VNG Insider (CLAUDE.md mục 3): tone hài duyên,
hashtag cố định #VNG #VNGCampus #Starter, clip_tag theo kho clip Nghi own.
"""

# [A] Scout chưa wire vào ChannelBuilder — trend digest mock dùng cho CẢ 2 mode.
TREND_DIGEST = {
    "nguon": "mock — Scout chưa wire vào ChannelBuilder (repo tiktok-scout riêng)",
    "hook_pattern_thang": [
        "POV ngày đầu đi làm",
        "Câu hỏi mở “Bạn có biết…”",
    ],
    "format_trend": [
        {"name": "POV office tour", "retention_estimate": 0.70},
        {"name": "Tip vào công ty tech", "retention_estimate": 0.66},
    ],
    "benchmark": {"metric": "retention_3s", "nguong": 0.65},
}

IDEAS_RESULT = {
    "status": "ok",
    "error": None,
    "ideas": [
        {
            "id": "idea_01",
            "title": "POV: ngày đầu làm Starter ở VNG Campus",
            "pillar": "campus",
            "angle": "Theo chân fresher từ cổng campus: check-in, góc làm việc, canteen giờ trưa.",
            "est_fit": 0.86,
        },
        {
            "id": "idea_02",
            "title": "3 thứ ở VNG Campus mà công ty khác không có",
            "pillar": "campus",
            "angle": "Đếm ngược 3 tiện ích: hồ bơi, gym, không gian mở giữa văn phòng.",
            "est_fit": 0.81,
        },
        {
            "id": "idea_03",
            "title": "Nộp CV vào VNG thì chuyện gì xảy ra?",
            "pillar": "tuyendung",
            "angle": "Giải thích nhanh các vòng tuyển dụng dưới góc nhìn một Starter từng trải.",
            "est_fit": 0.78,
        },
    ],
}

SCRIPT_RESULT = {
    "status": "ok",
    "error": None,
    "warnings": [],
    "package": {
        "idea": IDEAS_RESULT["ideas"][0],
        "script": (
            "Ngày đầu vào VNG, tôi cứ nghĩ công ty tech nào cũng giống nhau. "
            "Cho tới khi bước qua cổng campus. Cây xanh nhiều hơn cả công viên gần nhà tôi. "
            "Check-in xong, anh buddy dẫn đi một vòng. Góc làm việc nhìn thẳng ra khoảng sân mở, "
            "ngồi code mà tưởng đang ngồi cafe. Trưa xuống canteen, đồ ăn nhiều món hơn cả food court. "
            "Chiều mệt thì xuống gym hoặc ra góc cây xanh ngồi thở. "
            "Điều bất ngờ nhất? Mọi người gọi nhau là Starter — vì ở đây ai cũng đang bắt đầu một thứ gì đó. "
            "Ngày đầu của bạn ở công ty cũ thế nào, kể tôi nghe với."
        ),
        "text_hook": "Ngày đầu làm Starter ở VNG 👀",
        "caption": "Ngày đầu ở VNG Campus có gì? Theo chân Starter mới toanh một vòng nhé!",
        "hashtags": ["#VNG", "#VNGCampus", "#Starter"],
        "shot_list": [
            {"line": 1, "voiceover": "Ngày đầu vào VNG, tôi cứ nghĩ công ty tech nào cũng giống nhau.",
             "duration_sec": 4, "clip_tag": "campusngoaicanh", "scene_hint": "cổng campus, toàn cảnh"},
            {"line": 2, "voiceover": "Cho tới khi bước qua cổng campus. Cây xanh nhiều hơn cả công viên gần nhà tôi.",
             "duration_sec": 5, "clip_tag": "cayxanhthugian", "scene_hint": "mảng xanh trong campus"},
            {"line": 3, "voiceover": "Góc làm việc nhìn thẳng ra khoảng sân mở, ngồi code mà tưởng đang ngồi cafe.",
             "duration_sec": 6, "clip_tag": "goclamviec", "alt_tag": "khonggianmo", "scene_hint": "desk + view sân mở"},
            {"line": 4, "voiceover": "Trưa xuống canteen, đồ ăn nhiều món hơn cả food court.",
             "duration_sec": 5, "clip_tag": "canteencafe", "scene_hint": "canteen giờ trưa"},
            {"line": 5, "voiceover": "Chiều mệt thì xuống gym hoặc ra góc cây xanh ngồi thở.",
             "duration_sec": 5, "clip_tag": "gym", "alt_tag": "cayxanhthugian", "scene_hint": "gym nhanh, cắt cảnh"},
            {"line": 6, "voiceover": "Mọi người gọi nhau là Starter — vì ở đây ai cũng đang bắt đầu một thứ gì đó.",
             "duration_sec": 6, "clip_tag": "khonggianmo", "scene_hint": "người qua lại không gian mở"},
        ],
    },
}

# Producer mock — simulate progress 6 bước cho UI vẽ progress bar.
PRODUCE_PROGRESS = [
    (2, "[1/6] Đang sinh giọng đọc (ElevenLabs TTS)..."),
    (25, "[2/6] LLM chọn clip từ kho..."),
    (45, "[3/6] Ghép clip (mute tiếng gốc)..."),
    (65, "[4/6] Khớp độ dài video với giọng đọc..."),
    (80, "[5/6] Mux giọng đọc + burn phụ đề..."),
    (95, "[6/6] Upload MinIO outputs..."),
]

PRODUCE_RESULT = {
    "run_id": "mockproduce1",
    "voice_url": None,
    "silent_video_url": None,
    "output_url": None,  # mock không render file thật
    "voice_duration_sec": 46.8,
    "silent_video_duration_sec": 47.5,
    "final_duration_sec": 47.1,
    "selected_clips": ["campus_001", "cayxanh_002", "goclamviec_003", "canteen_001", "gym_001"],
    "alignment": {"action": "trim"},
    "subtitles": True,
    "subtitle_chunks": 28,
    "tts_cache_hit": True,
    "stage_timings_sec": {"tts": 0.5, "llm-pick": 0.5, "concat": 0.5,
                          "align": 0.5, "mux": 0.5, "upload": 0.5},
    "total_elapsed_sec": 3.0,
}

PUBLISH_RESULT = {
    "status": "published",
    "publish_id": "mock_publish_001",
    "video_id": "mock_video_001",
    "error": None,
}

METRICS_RESULT = {
    "status": "ok",
    "error": None,
    "videos": [{
        "id": "mock_video_001",
        "view_count": 1240, "like_count": 96,
        "comment_count": 14, "share_count": 7,
    }],
}
