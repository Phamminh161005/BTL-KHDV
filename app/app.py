"""Giao diện xem lịch thi (Streamlit).

Người phụ trách: Mạnh. Đây mới là khung tối thiểu: đọc schedule.json và hiển thị bảng lượt thi.
Định dạng file kết quả: docs/data_schema.md mục 7.

Cách chạy:
    streamlit run app/app.py
"""
import json
import os

import streamlit as st

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "toy", "schedule.json")

st.set_page_config(page_title="Lịch thi", layout="wide")
st.title("Lịch thi cuối kỳ")

path = st.text_input("Đường dẫn file kết quả", os.path.normpath(DEFAULT_PATH))
if not os.path.exists(path):
    st.error(f"Không tìm thấy file {path}")
    st.stop()

with open(path, encoding="utf-8") as f:
    schedule = json.load(f)

col1, col2, col3 = st.columns(3)
col1.metric("Trạng thái", schedule["status"])
col2.metric("Giá trị mục tiêu", schedule["objective"])
col3.metric("Số lượt thi", len(schedule["sittings"]))

st.subheader("Các lượt thi")
st.dataframe([
    {
        "Ngày": s["date"],
        "Giờ": f"{s['start_time']}–{s['end_time']}",
        "Môn": f"{s['course_id']} {s['course_name']}",
        "Số SV": s["num_students"],
        "Phòng": ", ".join(r["room_id"] for r in s["rooms"]),
        "Giám thị": "; ".join(", ".join(r["proctors"]) for r in s["rooms"]),
    }
    for s in schedule["sittings"]
], width="stretch")

# TODO: xem theo phòng, theo sinh viên, theo giám thị; hiển thị KPI và thông báo
