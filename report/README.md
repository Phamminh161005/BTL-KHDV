# Báo cáo

Báo cáo viết bằng LaTeX, biên dịch bằng XeLaTeX.

## Biên dịch

Trên Overleaf: nén thư mục `report/` thành file zip, tạo project bằng New Project → Upload Project. File `latexmkrc` đã chọn sẵn XeLaTeX.

Trên máy (cần TeX Live hoặc MiKTeX):

```powershell
cd report
latexmk main.tex
```

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| `main.tex` | File chính: khai báo gói, ghép các chương |
| `macros.tex` | Lệnh dùng chung (`\code`, `\todo`, `\rb`) |
| `frontmatter/` | Bìa, phân công, tóm tắt, ký hiệu |
| `chapters/` | Tám chương, mỗi chương một file |
| `appendices/` | Phụ lục A, B, C |
| `figures/` | Hình (PNG, PDF) |
| `tables/` | Bảng dài tách riêng, chèn bằng `\input{tables/...}` |
| `references.bib` | Tài liệu tham khảo |

## Phân công theo chương

Khỏe làm slide và thuyết trình, không viết báo cáo.

| File | Người viết |
|---|---|
| `01-gioi-thieu`, `02-phan-tich-dich-vu`, `04-he-thong`, `06-cong-cu-mon-hoc`, phụ lục A | Mạnh |
| `03-mo-hinh`, `05-thuc-nghiem`, `07-danh-gia`, `08-ket-luan`, phụ lục B, phụ lục C, phần đầu | Minh |

Đầu mỗi file có chú thích ghi nguồn tài liệu và số liệu cần dùng.

## Quy ước viết

- Mỗi người chỉ sửa file chương của mình, để tránh xung đột khi gộp nhánh.
- Đặt nhãn theo dạng `ch:`, `sec:`, `subsec:`, `fig:`, `tab:`, `eq:`, tham chiếu bằng `\ref`.
- Số liệu lấy từ `experiments/results/`, không gõ tay từ trí nhớ.
- Không in đậm từ ngữ ở giữa câu.
- Chỗ chưa xong ghi `\todo{...}` (hiện chữ đỏ); xóa hết trước khi nộp.
