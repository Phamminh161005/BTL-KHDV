# Quy ước làm việc nhóm

## 1. Quy trình cho mỗi task

1. Nhận task trên Coreach. Mỗi task có một mã, ví dụ `T2`.
2. Cập nhật nhánh `main` mới nhất rồi tạo nhánh riêng cho task:

   ```powershell
   git checkout main
   git pull
   git checkout -b T2-exam-solver
   ```

   Tên nhánh bắt đầu bằng mã task, sau đó là vài chữ mô tả không dấu, nối bằng dấu gạch ngang.
3. Làm việc, commit thường xuyên trên nhánh đó.
4. Đẩy nhánh lên GitHub và tạo Pull Request vào `main`:

   ```powershell
   git push -u origin T2-exam-solver
   ```

   Tiêu đề Pull Request bắt đầu bằng mã task, ví dụ `T2: Solver bài toán A, chiến lược single`. Phần mô tả ghi: đã làm gì, chạy thử thế nào, còn gì chưa làm.
5. Ít nhất một thành viên khác duyệt (Approve) thì mới gộp (Merge) vào `main`.
6. Chuyển task trên Coreach sang Done sau khi đã gộp.

Không commit thẳng vào `main`.

## 2. Điều kiện để một task được tính là xong

- `pytest` chạy qua trên máy người làm.
- Code bám đúng tài liệu trong `docs/`. Nếu cần làm khác tài liệu, sửa tài liệu trước trong cùng Pull Request và nêu rõ lý do trong mô tả.
- Pull Request đã được duyệt và gộp vào `main`.
- Thành phần mới có kiểm thử trong `tests/` nếu kiểm thử được.

## 3. Commit

- Viết tiếng Việt có dấu, một dòng ngắn nói đã làm gì, ví dụ `Thêm ràng buộc A-H2 cho sinh viên`.
- Mỗi commit làm một việc. Không gộp nhiều thay đổi không liên quan vào một commit.
- Không commit file sinh ra khi chạy (đã có `.gitignore`), trừ `output/toy/schedule.json` là kết quả tham chiếu.

## 4. Viết code

- Python 3.11 trở lên. Tên biến, tên hàm bằng tiếng Anh; chú thích và thông báo bằng tiếng Việt.
- Code cài đặt một ràng buộc thì ghi mã ràng buộc ở chú thích ngay trên, ví dụ `# A-H2: không sinh viên nào thi hai lượt trùng ca`.
- Dùng lại các hàm có sẵn trong `src/instance.py` (`rooms_for`, `start_slots`, `covered`, ...) thay vì tự viết lại.
- Mã định danh luôn là chuỗi; nếu dùng pandas để đọc CSV thì bắt buộc `dtype=str`.
- Không sửa `src/validator.py` để làm cho solver "qua kiểm thử". Validator là trọng tài; nếu nghi validator sai, báo trưởng nhóm.

## 5. Tài liệu và báo cáo

- Tài liệu kỹ thuật viết Markdown trong `docs/`, đọc bằng `Ctrl+Shift+V` trong VS Code.
- Không in đậm từ ngữ ở giữa câu để nhấn mạnh; dùng tiêu đề, bảng, danh sách.
- Báo cáo và hình vẽ đặt trong `report/`.
