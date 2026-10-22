# Phạm vi đề tài

**Đề tài:** Hệ thống xếp lịch phòng thi và phòng máy học phần

> Tài liệu này trả lời câu hỏi "nhóm làm đến đâu". Mọi task trên Coreach phải nằm trong phạm vi này.
> Muốn thêm/bớt gì thì sửa tài liệu này trước (qua Pull Request), rồi mới tạo task.

---

## 1. Mục tiêu

Xây dựng một hệ thống dịch vụ xếp lịch cho phòng đào tạo của một khoa:

1. Nhận dữ liệu: phòng, học phần, sinh viên đăng ký, giảng viên, các ca/buổi.
2. Dùng mô hình quy hoạch nguyên tuyến tính (ILP) để tự động tạo:
   - Bài toán A, lịch thi cuối kỳ: môn nào thi ca nào, ở phòng nào, giám thị nào coi.
   - Bài toán B, lịch phòng học/phòng máy theo tuần: lớp học phần nào học phòng nào, buổi nào.
3. Lịch tạo ra không có xung đột (thỏa mọi ràng buộc cứng) và tốt nhất có thể theo các tiêu chí chất lượng dịch vụ (ràng buộc mềm).
4. Đánh giá hệ thống bằng các chỉ số chất lượng dịch vụ (KPI) và các công cụ của môn học (tối ưu hóa, hàng đợi, tồn kho, SOA, mô hình hộp trắng).

Thứ tự ưu tiên: bài toán A làm trước và phải hoàn chỉnh. Bài toán B làm sau, dùng lại dữ liệu và code của A.

## 2. Bối cảnh và các bên liên quan

| Bên liên quan | Vai trò | Họ cần gì từ hệ thống |
|---|---|---|
| Phòng đào tạo / giáo vụ khoa | Người vận hành dịch vụ | Tạo lịch nhanh, không xung đột, sửa lịch dễ khi có sự cố |
| Sinh viên | Khách hàng chính | Không trùng lịch thi, các môn thi cách xa nhau, biết lịch sớm |
| Giảng viên / giám thị | Nguồn lực + người dùng | Không bị xếp trùng, được tôn trọng lịch bận, chia đều buổi coi thi |
| Kỹ thuật viên phòng máy | Nguồn lực | Phòng máy không bị khai thác quá tải, có thời gian bảo trì |

## 3. Quy mô dữ liệu

Toàn bộ dùng dữ liệu giả lập, sinh bằng script, quy mô gần với một khoa thật. Ba mức:

| Bộ dữ liệu | Học phần | Phòng (trong đó phòng máy) | Sinh viên | Mục đích |
|---|---|---|---|---|
| `toy` | 5 | 3 (1) | ~50 | Kiểm thử, có đáp án tính tay, minh họa báo cáo |
| `medium` | 30 | 10 (3) | ~500 | Demo chính |
| `large` | 60 | 15 (4) | ~1.000 | Thử khả năng mở rộng, đo thời gian giải |

## 4. Giả định

### 4.1. Chung

- Phạm vi một khoa, một học kỳ. Không xét phòng dùng chung với khoa khác.
- Mỗi phòng có: sức chứa (ghế), sức chứa khi thi, có phải phòng máy không, số máy.
- Dữ liệu đầu vào là file CSV; định dạng chi tiết ở `docs/data_schema.md`.

### 4.2. Khung giờ ca

Lịch thi và lịch học dùng chung khung 4 ca mỗi ngày, mỗi ca dài 150 phút:

| Ca | Giờ | Buổi |
|---|---|---|
| 1 | 07:00 – 09:30 | Sáng |
| 2 | 09:30 – 12:00 | Sáng |
| 3 | 13:00 – 15:30 | Chiều |
| 4 | 15:30 – 18:00 | Chiều |

Ca 1 và ca 2 liền nhau, ca 3 và ca 4 liền nhau. Giữa ca 2 và ca 3 là giờ nghỉ trưa.

### 4.3. Bài toán A, lịch thi

- Đợt thi kéo dài 2 tuần, mỗi tuần 6 ngày (Thứ 2 – Thứ 7), mỗi ngày 4 ca → 48 ca.
- Trong 150 phút của một ca, thời gian làm bài tối đa là 120 phút. 30 phút còn lại dành cho gọi tên, phát đề, thu bài và chuyển ca.
- Mỗi môn chỉ thi một lần. Số ca một môn chiếm phụ thuộc vào thời lượng làm bài:

  | Thời lượng làm bài | Số ca chiếm | Cách xếp |
  |---|---|---|
  | Đến 120 phút | 1 ca | Bất kỳ ca nào |
  | Từ 121 đến 270 phút | 2 ca liên tiếp | Ca 1 + 2 (cả buổi sáng) hoặc ca 3 + 4 (cả buổi chiều) |
  | Trên 270 phút | Không hỗ trợ | Ngoài phạm vi, thực tế hầu như không có |

  Môn chiếm 2 ca không được kéo qua giờ nghỉ trưa, tức là không xếp ca 2 + 3.
- Sức chứa khi thi = 1/2 số ghế (giãn cách), phòng máy = số máy hoạt động.
- Một môn đông có thể chia ra nhiều phòng trong cùng ca.
- Hình thức thi của mỗi môn đã biết trước: thi viết (phòng thường) hoặc thi trên máy (phòng máy).
- Mỗi phòng thi cần 2 giám thị. Giám thị là giảng viên của khoa; mỗi giảng viên có danh sách ca bận.

### 4.4. Bài toán B, lịch phòng học/phòng máy

- Lịch lặp lại theo tuần: 6 ngày × 4 ca/ngày = 24 ca/tuần, theo khung giờ ở mục 4.2.
- Mỗi buổi học chiếm 1 ca.
- Mỗi lớp học phần có số buổi/tuần, sĩ số, có cần phòng máy hay không, giảng viên phụ trách.
- Giờ học lý thuyết và thực hành của cùng một học phần được tách thành các lớp riêng.

## 5. Trong phạm vi / Ngoài phạm vi

| ✅ Trong phạm vi | ❌ Ngoài phạm vi |
|---|---|
| Mô hình ILP cho bài toán A và B | Đăng nhập, phân quyền người dùng |
| Xếp giám thị cho lịch thi | Cơ sở dữ liệu thật (dùng CSV/JSON) |
| Giải bằng OR-Tools CP-SAT | Dữ liệu thật của khoa |
| So sánh với PuLP/CBC (nếu kịp) | Kết nối hệ thống đào tạo thật của trường |
| Script sinh dữ liệu giả lập | Xếp lịch giảng dạy toàn trường |
| Hàm kiểm tra lời giải (validator) và tính KPI | Ứng dụng di động |
| Giao diện web demo (Streamlit): tải dữ liệu, chạy, xem lịch, xuất Excel | Gửi thông báo/email thật |
| Kịch bản sự cố: phòng hỏng, thêm lớp → xếp lại | Môn thi dài hơn 270 phút |
| Phân tích dịch vụ và đánh giá theo các chương của môn | Tối ưu hóa thời gian thực cho cả năm học |

## 6. Ràng buộc (tóm tắt)

Đặc tả toán học đầy đủ nằm ở `docs/model_spec.md`. Mã ràng buộc dùng chung trong code, báo cáo và trao đổi.

### 6.1. Bài toán A, lịch thi

| Mã | Loại | Nội dung |
|---|---|---|
| A-H1 | Cứng | Mỗi môn được xếp đúng một lần thi; môn dài chiếm 2 ca liên tiếp cùng buổi theo mục 4.3 |
| A-H2 | Cứng | Không sinh viên nào có 2 môn thi trùng ca |
| A-H3 | Cứng | Tổng sức chứa các phòng của một môn ≥ số sinh viên môn đó |
| A-H4 | Cứng | Mỗi phòng, mỗi ca chỉ dành cho tối đa 1 môn |
| A-H5 | Cứng | Môn thi trên máy chỉ xếp vào phòng máy |
| A-H6 | Cứng | Không xếp vào ca phòng đã báo bận |
| A-H7 | Cứng | Mỗi phòng thi đang dùng có đủ 2 giám thị |
| A-H8 | Cứng | Một giám thị không coi 2 phòng cùng ca, không bị xếp vào ca bận |
| A-S1 | Mềm | Hạn chế sinh viên thi ≥ 2 môn trong một ngày |
| A-S2 | Mềm | Giãn cách các môn thi của cùng một sinh viên |
| A-S3 | Mềm | Hạn chế chia một môn ra quá nhiều phòng |
| A-S4 | Mềm | Hạn chế lãng phí chỗ (phòng quá to so với số SV) |
| A-S5 | Mềm | Chia đều số buổi coi thi giữa các giám thị |

Với môn chiếm 2 ca, các ràng buộc A-H2, A-H4, A-H6 và A-H8 áp dụng cho cả hai ca: phòng, sinh viên và giám thị đều bận suốt hai ca đó.

### 6.2. Bài toán B, lịch phòng học/phòng máy

| Mã | Loại | Nội dung |
|---|---|---|
| B-H1 | Cứng | Mỗi lớp được xếp đủ số buổi/tuần |
| B-H2 | Cứng | Mỗi phòng, mỗi ca tối đa 1 lớp |
| B-H3 | Cứng | Sĩ số ≤ sức chứa phòng (phòng máy: ≤ số máy) |
| B-H4 | Cứng | Lớp thực hành chỉ xếp vào phòng máy |
| B-H5 | Cứng | Giảng viên không dạy 2 lớp cùng ca, không xếp vào ca bận |
| B-S1 | Mềm | Hạn chế lãng phí chỗ |
| B-S2 | Mềm | Tôn trọng nguyện vọng giờ dạy của giảng viên |
| B-S3 | Mềm | Các buổi của cùng một lớp không nằm cùng ngày |
| B-S4 | Mềm | Giữ hệ số sử dụng phòng máy ≤ 85% để có dự phòng |

## 7. Chỉ số đánh giá (KPI)

| KPI | Ý nghĩa dịch vụ | Mục tiêu |
|---|---|---|
| Số vi phạm ràng buộc cứng | Lịch có dùng được không | = 0 |
| Số SV thi ≥ 2 môn/ngày | Trải nghiệm sinh viên | Càng nhỏ càng tốt |
| Khoảng cách TB giữa 2 môn thi liên tiếp của SV | Trải nghiệm sinh viên | Càng lớn càng tốt |
| Chênh lệch số buổi coi thi giữa các giám thị | Công bằng cho giảng viên | Càng nhỏ càng tốt |
| Hệ số sử dụng phòng / phòng máy (ρ) | Hiệu quả nguồn lực (Ch.3) | 60–85% |
| Tỷ lệ lấp đầy chỗ ngồi | Lãng phí tài nguyên (Ch.5) | Càng cao càng tốt |
| Thời gian tạo lịch | Năng suất dịch vụ | < 5 phút với bộ `large` |
| Thời gian xếp lại khi có sự cố | Khả năng phục hồi dịch vụ | < 1 phút |

## 8. Công nghệ

- Ngôn ngữ: Python 3.11+
- Bộ giải chính: Google OR-Tools (CP-SAT)
- Bộ giải đối chứng: PuLP + CBC
- Dữ liệu: pandas, CSV/JSON
- Giao diện: Streamlit
- Quản lý mã nguồn: GitHub (repo này)
- Quản lý công việc: Coreach

## 9. Sản phẩm bàn giao

1. Mã nguồn trên GitHub, chạy được theo hướng dẫn trong `README.md`.
2. Ba bộ dữ liệu `toy`, `medium`, `large` + script sinh dữ liệu.
3. Giao diện demo.
4. Báo cáo (phân tích dịch vụ, mô hình, thực nghiệm, đánh giá).
5. Slide thuyết trình + video demo dự phòng.
