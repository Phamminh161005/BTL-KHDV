# Đặc tả mô hình toán

Tài liệu này viết các quy tắc trong `docs/scope.md` thành mô hình quy hoạch nguyên tuyến tính (ILP). Code solver, validator và chương mô hình trong báo cáo đều phải bám đúng tài liệu này. Mỗi ràng buộc mang đúng mã đã đặt trong scope (A-H1, A-S1, ...).

Phiên bản hiện tại mới có bài toán A (lịch thi). Bài toán B (lịch phòng học/phòng máy) sẽ được bổ sung ở phiên bản sau, theo cùng cách trình bày.

Công thức viết bằng LaTeX. Xem trong VS Code bằng `Ctrl+Shift+V`; GitHub cũng hiển thị được.

---

## A. Bài toán lịch thi

### A.1. Ý tưởng chính

Mô hình trả lời bốn câu hỏi:

1. Mỗi môn có những lượt thi nào, mỗi lượt bắt đầu ở ca nào?
2. Mỗi lượt dùng những phòng nào?
3. Với môn được chia lượt, mỗi sinh viên thi lượt nào?
4. Mỗi phòng đang thi ở mỗi ca do hai giám thị nào coi?

Một lượt thi được xác định bằng cặp (môn, ca bắt đầu). Nói cách khác, không đánh số "lượt 1, lượt 2" mà chỉ hỏi "môn $c$ có một lượt bắt đầu ở ca $s$ hay không". Cách này có ba lợi ích:

- Hai lượt của cùng một môn không thể trùng ca bắt đầu, nên không cần thêm ràng buộc để tách chúng.
- Không sinh ra các lời giải đối xứng kiểu "đổi tên lượt 1 thành lượt 2", giúp solver chạy nhanh hơn.
- Ràng buộc trùng lịch của sinh viên viết được dưới dạng tuyến tính mà không phải nhân hai biến với nhau (xem A.5, A-H2).

### A.2. Tập hợp và chỉ số

| Ký hiệu | Ý nghĩa |
|---|---|
| $D$ | Tập ngày thi (12 ngày: 2 tuần, Thứ 2 đến Thứ 7), chỉ số $d$ |
| $T$ | Tập các ca thi dùng được, chỉ số $t$ hoặc $s$. Các ca rơi vào ngày nghỉ của toàn khoa đã bị loại khỏi $T$ |
| $T_d \subseteq T$ | Các ca thuộc ngày $d$ |
| $k(t) \in \{1,2,3,4\}$ | Thứ tự của ca $t$ trong ngày |
| $t^{+}$ | Ca kế tiếp của $t$ trong cùng buổi: nếu $k(t)=1$ thì là ca 2 cùng ngày, nếu $k(t)=3$ thì là ca 4 cùng ngày; không định nghĩa với $k(t) \in \{2,4\}$ |
| $C$ | Tập môn thi, chỉ số $c$. Các lớp học phần của cùng một học phần đã được gộp thành một môn |
| $C^{V}, C^{M}$ | Môn thi viết, môn thi trên máy. $C = C^{V} \cup C^{M}$, hai tập không giao nhau |
| $C^{P}$ | Môn được phép chia lượt, tức $L_c \ge 2$ (xem tham số) |
| $C^{U}$ | Môn chỉ có một lượt, $C^{U} = C \setminus C^{P}$ |
| $R$ | Tập phòng, chỉ số $r$ |
| $R^{V}, R^{M}$ | Phòng thường, phòng máy. $R = R^{V} \cup R^{M}$, hai tập không giao nhau |
| $R_c$ | Phòng phù hợp với môn $c$: $R_c = R^{V}$ nếu $c \in C^{V}$, $R_c = R^{M}$ nếu $c \in C^{M}$ |
| $I$ | Tập sinh viên, chỉ số $i$ |
| $I_c$ | Sinh viên đăng ký môn $c$ |
| $C_i$ | Các môn sinh viên $i$ đăng ký |
| $G$ | Tập giảng viên tham gia coi thi, chỉ số $g$ |
| $Q$ | Tập cặp ngày thi $(d, d')$ với $d'$ là ngày ngay sau $d$ theo lịch, ví dụ Thứ 2–Thứ 3. Thứ 7 và Thứ 2 tuần sau không phải cặp vì có Chủ nhật ở giữa; tương tự nếu Thứ 4 nghỉ lễ thì Thứ 3 và Thứ 5 không phải cặp, vì sinh viên có ngày nghỉ ở giữa để ôn |

### A.3. Tham số (dữ liệu biết trước)

| Ký hiệu | Ý nghĩa | Ghi chú |
|---|---|---|
| $\tau_c$ | Thời lượng làm bài của môn $c$ (phút) | |
| $\ell_c \in \{1,2\}$ | Số ca mỗi lượt của môn $c$ chiếm | $\ell_c = 1$ nếu $\tau_c \le 120$; $\ell_c = 2$ nếu $120 < \tau_c \le 280$. Môn có $\tau_c > 280$ bị loại ở bước kiểm tra trước (A.8) |
| $L_c \ge 1$ | Số lượt tối đa của môn $c$ | Môn thi viết mặc định $L_c = 1$; chỉ lớn hơn 1 khi dữ liệu đánh dấu cho phép chia |
| $n_c$ | Số sinh viên của môn $c$, $n_c = \lvert I_c \rvert$ | |
| $\kappa_r$ | Sức chứa khi thi của phòng $r$ | Số nguyên. Mặc định $\lfloor$số ghế$/2\rfloor$ với phòng thường, bằng số máy đang hoạt động với phòng máy |
| $B^{R}_r \subseteq T$ | Các ca phòng $r$ bận | |
| $B^{G}_g \subseteq T$ | Các ca giảng viên $g$ bận | |
| $\Phi_g \subseteq C$ | Các môn giảng viên $g$ dạy | Chỉ dùng khi bật A-H10 |
| $\nu = 2$ | Số giám thị mỗi phòng | |
| $\theta \in \{0,1\}$ | Bật/tắt A-H10 | Mặc định $\theta = 0$ |
| $\omega_1, \dots, \omega_6$ | Trọng số các ràng buộc mềm | Số nguyên, xem A.6 |

Từ các tham số trên, định nghĩa thêm hai tập dẫn xuất:

- Tập ca được phép bắt đầu của môn $c$:

$$
S_c =
\begin{cases}
T & \text{nếu } \ell_c = 1 \\
\{\, s \in T : k(s) \in \{1,3\} \text{ và } s^{+} \in T \,\} & \text{nếu } \ell_c = 2
\end{cases}
$$

- Tập ca bị chiếm khi lượt của môn $c$ bắt đầu ở ca $s$:

$$
\mathrm{Cov}(c,s) =
\begin{cases}
\{s\} & \text{nếu } \ell_c = 1 \\
\{s, s^{+}\} & \text{nếu } \ell_c = 2
\end{cases}
$$

- Ngược lại, các ca bắt đầu của môn $c$ mà lượt đó đang diễn ra ở ca $t$:

$$
S_c(t) = \{\, s \in S_c : t \in \mathrm{Cov}(c,s) \,\}
$$

Ví dụ: môn 180 phút có $\ell_c = 2$. Nó chỉ được bắt đầu ở ca 1 hoặc ca 3. Nếu bắt đầu ở ca 1 ngày Thứ 2 thì chiếm ca 1 và ca 2 của ngày đó. Ở ca 2 ngày Thứ 2, $S_c(t)$ chứa đúng ca 1 ngày Thứ 2.

Điều kiện $s^{+} \in T$ đảm bảo lượt 2 ca không bắt đầu ở ca 1 nếu ca 2 cùng ngày đã bị loại (ngày nghỉ nửa buổi chẳng hạn), và không bao giờ vắt qua giờ nghỉ trưa hay sang ngày hôm sau.

### A.4. Biến quyết định

| Biến | Miền | Ý nghĩa |
|---|---|---|
| $x_{c,s}$ | $\{0,1\}$, với $c \in C,\ s \in S_c$ | Bằng 1 nếu môn $c$ có một lượt bắt đầu ở ca $s$ |
| $u_{c,r,s}$ | $\{0,1\}$, với $c \in C,\ r \in R_c,\ s \in S_c$ | Bằng 1 nếu lượt $(c,s)$ dùng phòng $r$ |
| $q_{i,c,s}$ | $\{0,1\}$, với $c \in C^{P},\ i \in I_c,\ s \in S_c$ | Bằng 1 nếu sinh viên $i$ thi môn $c$ ở lượt bắt đầu ca $s$. Chỉ tồn tại với môn được chia lượt |
| $w_{g,r,t}$ | $\{0,1\}$, với $g \in G,\ r \in R,\ t \in T$ | Bằng 1 nếu giám thị $g$ coi phòng $r$ ở ca $t$ |
| $a_{i,d}$ | Số nguyên $\ge 0$ | Biến phụ cho A-S1 |
| $b_{i,d}$ | Số nguyên $\ge 0$ | Biến phụ cho A-S2 |
| $\Lambda^{\max}, \Lambda^{\min}$ | Số nguyên $\ge 0$ | Biến phụ cho A-S5 |

Biến $u$ chỉ được tạo với $r \in R_c$. Vì vậy ràng buộc A-H5 (đúng loại phòng) được đảm bảo ngay từ cách khai báo biến.

Với môn chỉ có một lượt ($c \in C^{U}$), mọi sinh viên của môn đều thi lượt đó, nên không cần biến $q$. Để viết gọn, dùng các biểu thức sau:

- Sinh viên $i$ có thi môn $c$ ở lượt bắt đầu ca $s$ hay không:

$$
\pi_{i,c,s} =
\begin{cases}
x_{c,s} & \text{nếu } c \in C^{U} \\
q_{i,c,s} & \text{nếu } c \in C^{P}
\end{cases}
$$

- Số sinh viên của lượt $(c,s)$:

$$
N_{c,s} =
\begin{cases}
n_c \, x_{c,s} & \text{nếu } c \in C^{U} \\
\sum_{i \in I_c} q_{i,c,s} & \text{nếu } c \in C^{P}
\end{cases}
$$

- Phòng $r$ có đang được dùng ở ca $t$ hay không:

$$
o_{r,t} = \sum_{c \in C : r \in R_c} \ \sum_{s \in S_c(t)} u_{c,r,s}
$$

- Số lượt sinh viên $i$ bắt đầu trong ngày $d$ (lượt 2 ca chỉ tính một lần vì chỉ đếm ca bắt đầu):

$$
E_{i,d} = \sum_{c \in C_i} \ \sum_{s \in S_c \cap T_d} \pi_{i,c,s}
$$

- Số ca coi thi của giám thị $g$:

$$
\lambda_g = \sum_{r \in R} \sum_{t \in T} w_{g,r,t}
$$

Tất cả các biểu thức trên đều tuyến tính theo biến.

### A.5. Ràng buộc cứng

#### A-H1. Số lượt của mỗi môn

Mỗi môn có ít nhất 1 lượt và không quá $L_c$ lượt. Với môn chỉ có một lượt, ràng buộc này trở thành "đúng 1 lượt".

$$
1 \le \sum_{s \in S_c} x_{c,s} \le L_c \qquad \forall c \in C
$$

Việc mỗi lượt chiếm 1 hay 2 ca, và lượt 2 ca chỉ bắt đầu ở ca 1 hoặc ca 3, đã nằm sẵn trong định nghĩa $S_c$ và $\mathrm{Cov}(c,s)$.

#### A-H9. Mỗi sinh viên thi đúng một lượt của môn được chia lượt

Với $c \in C^{P}$:

$$
\sum_{s \in S_c} q_{i,c,s} = 1 \qquad \forall c \in C^{P},\ i \in I_c
$$

$$
q_{i,c,s} \le x_{c,s} \qquad \forall c \in C^{P},\ i \in I_c,\ s \in S_c
$$

$$
x_{c,s} \le \sum_{i \in I_c} q_{i,c,s} \qquad \forall c \in C^{P},\ s \in S_c
$$

Ràng buộc thứ nhất: mỗi sinh viên được xếp đúng một lượt. Ràng buộc thứ hai: chỉ được xếp vào lượt có mở. Ràng buộc thứ ba: không mở lượt nào mà không có sinh viên (tránh lượt rỗng vẫn chiếm phòng và giám thị).

Với $c \in C^{U}$, A-H9 tự động đúng vì $\pi_{i,c,s} = x_{c,s}$ và môn có đúng một lượt.

#### A-H2. Không sinh viên nào thi hai lượt trùng ca

$$
\sum_{c \in C_i} \ \sum_{s \in S_c(t)} \pi_{i,c,s} \le 1 \qquad \forall i \in I,\ t \in T
$$

Tổng bên trái đếm số lượt sinh viên $i$ đang ngồi thi ở ca $t$, kể cả lượt 2 ca đã bắt đầu từ ca trước. Nhờ dùng $q_{i,c,s}$ (sinh viên gắn trực tiếp với ca bắt đầu) nên ràng buộc vẫn tuyến tính với môn chia lượt.

#### A-H3. Đủ chỗ cho mỗi lượt

$$
N_{c,s} \le \sum_{r \in R_c} \kappa_r \, u_{c,r,s} \qquad \forall c \in C,\ s \in S_c
$$

$$
u_{c,r,s} \le x_{c,s} \qquad \forall c \in C,\ r \in R_c,\ s \in S_c
$$

Ràng buộc thứ hai đảm bảo chỉ lượt có mở mới được giữ phòng. Ràng buộc này viết riêng cho từng phòng thay vì gộp thành $\sum_r u_{c,r,s} \le \lvert R_c \rvert \, x_{c,s}$, theo quy tắc 9 và 10 của Daskin (xem A.9).

Mô hình chỉ quyết định tổng số chỗ của mỗi lượt, không quyết định sinh viên nào ngồi phòng nào. Việc chia sinh viên vào từng phòng làm ở bước hậu xử lý (A.10) và luôn làm được, vì tổng sức chứa đã đủ.

#### A-H4. Mỗi phòng, mỗi ca tối đa một môn

$$
o_{r,t} \le 1 \qquad \forall r \in R,\ t \in T
$$

Vì $o_{r,t}$ tính cả các lượt 2 ca đang diễn ra, phòng của lượt 2 ca bị giữ suốt hai ca.

#### A-H5. Đúng loại phòng

Đảm bảo bằng miền của biến $u$: $u_{c,r,s}$ chỉ tồn tại khi $r \in R_c$. Do đó môn thi máy chỉ vào phòng máy, và phòng máy không bao giờ được gán cho môn thi viết.

#### A-H6. Không dùng phòng vào ca bận

$$
o_{r,t} = 0 \qquad \forall r \in R,\ t \in B^{R}_r
$$

Khi cài đặt, có thể không tạo biến $u_{c,r,s}$ nào có $\mathrm{Cov}(c,s) \cap B^{R}_r \neq \emptyset$. Hai cách cho cùng kết quả; cách sau làm mô hình nhỏ hơn.

#### A-H7. Đủ giám thị, và lượt 2 ca giữ nguyên giám thị

Mỗi phòng đang dùng có đúng $\nu = 2$ giám thị; phòng không dùng thì không có giám thị:

$$
\sum_{g \in G} w_{g,r,t} = \nu \, o_{r,t} \qquad \forall r \in R,\ t \in T
$$

Lượt 2 ca giữ nguyên giám thị ở cả hai ca. Gọi $m_{r,s} = \sum_{c \in C : \ell_c = 2,\ r \in R_c,\ s \in S_c} u_{c,r,s}$ là chỉ báo "có lượt 2 ca bắt đầu ở phòng $r$, ca $s$" (nhận giá trị 0 hoặc 1 nhờ A-H4). Khi đó:

$$
w_{g,r,s} - w_{g,r,s^{+}} \le 1 - m_{r,s} \qquad \forall g \in G,\ r \in R,\ s \in T \text{ với } k(s) \in \{1,3\},\ s^{+} \in T
$$

$$
w_{g,r,s^{+}} - w_{g,r,s} \le 1 - m_{r,s} \qquad \text{(cùng miền chỉ số)}
$$

Khi $m_{r,s} = 1$, hai bất đẳng thức buộc $w_{g,r,s} = w_{g,r,s^{+}}$ với mọi giám thị. Khi $m_{r,s} = 0$, chúng không ràng buộc gì (vế phải bằng 1). Vế phải chỉ dùng hằng số 1 chứ không phải một số M lớn, nên đây không phải ràng buộc big-M lỏng.

#### A-H8. Giám thị không coi hai nơi cùng lúc, không coi vào ca bận

$$
\sum_{r \in R} w_{g,r,t} \le 1 \qquad \forall g \in G,\ t \in T
$$

$$
w_{g,r,t} = 0 \qquad \forall g \in G,\ r \in R,\ t \in B^{G}_g
$$

Với lượt 2 ca, giám thị được giữ ở cả hai ca (A-H7), nên nếu giám thị bận một trong hai ca thì cũng không thể coi lượt đó.

#### A-H10. (Tùy chọn) Giám thị không coi môn mình dạy

Chỉ thêm khi $\theta = 1$:

$$
w_{g,r,t} + \sum_{c \in \Phi_g : r \in R_c} \ \sum_{s \in S_c(t)} u_{c,r,s} \le 1 \qquad \forall g \in G,\ r \in R,\ t \in T
$$

Nếu phòng $r$ ở ca $t$ đang thi một môn giảng viên $g$ dạy thì $w_{g,r,t} = 0$. Tổng thứ hai không vượt quá 1 nhờ A-H4.

#### Ràng buộc bổ trợ (không làm thay đổi tập nghiệm)

Số phòng đang dùng ở mỗi ca không vượt quá số giám thị rảnh chia cho 2:

$$
\sum_{r \in R} o_{r,t} \le \left\lfloor \frac{\lvert \{ g \in G : t \notin B^{G}_g \} \rvert}{\nu} \right\rfloor \qquad \forall t \in T
$$

Ràng buộc này suy ra được từ A-H7 và A-H8 nên không loại bỏ lời giải hợp lệ nào. Nó được thêm vào để solver phát hiện sớm trường hợp thiếu giám thị, và cần thiết cho chiến lược giải hai pha (A.7).

### A.6. Ràng buộc mềm và hàm mục tiêu

Mỗi ràng buộc mềm được đo bằng một đại lượng phạt $P_k \ge 0$.

#### A-S1. Thi từ 2 môn trở lên trong một ngày

$$
a_{i,d} \ge E_{i,d} - 1, \quad a_{i,d} \ge 0 \qquad \forall i \in I,\ d \in D
$$

$$
P_1 = \sum_{i \in I} \sum_{d \in D} a_{i,d}
$$

$a_{i,d}$ là số môn "thừa" trong ngày: thi 1 môn thì 0, thi 2 môn thì 1, thi 3 môn thì 2. Vì hàm mục tiêu cực tiểu hóa nên solver luôn đẩy $a_{i,d}$ xuống đúng bằng $\max(0, E_{i,d} - 1)$.

Lưu ý: $P_1$ đếm số môn thừa, còn KPI "số sinh viên thi từ 2 môn/ngày" trong scope đếm số sinh viên. Hai đại lượng khác nhau nhưng cùng chiều; KPI được tính lại từ lời giải ở bước hậu xử lý.

#### A-S2. Giãn cách giữa các môn

Trong mỗi cửa sổ hai ngày thi liên tiếp, sinh viên nên có tối đa một môn:

$$
b_{i,d} \ge E_{i,d} + E_{i,d'} - 1, \quad b_{i,d} \ge 0 \qquad \forall i \in I,\ (d,d') \in Q
$$

$$
P_2 = \sum_{i \in I} \sum_{(d,d') \in Q} b_{i,d}
$$

Hai môn cùng một ngày bị phạt ở cả A-S1 và A-S2. Điều này là cố ý: thi cùng ngày tệ hơn thi hai ngày liền nhau, nên phải chịu phạt nặng hơn.

#### A-S3. Chia một lượt ra quá nhiều phòng

Phạt mỗi phòng vượt quá phòng đầu tiên của một lượt:

$$
P_3 = \sum_{c \in C} \sum_{s \in S_c} \Big( \sum_{r \in R_c} u_{c,r,s} - x_{c,s} \Big)
$$

Mỗi số hạng không âm vì A-H3 buộc lượt có mở phải có ít nhất một phòng (trừ khi $N_{c,s} = 0$, điều mà A-H9 và $n_c \ge 1$ đã loại trừ).

#### A-S4. Lãng phí chỗ

Số chỗ trống nhân với số ca bị chiếm:

$$
P_4 = \sum_{c \in C} \sum_{s \in S_c} \ell_c \Big( \sum_{r \in R_c} \kappa_r \, u_{c,r,s} - N_{c,s} \Big)
$$

Mỗi số hạng không âm nhờ A-H3. Nhân với $\ell_c$ vì lượt 2 ca giữ chỗ trống suốt hai ca.

#### A-S5. Công bằng giữa các giám thị

$$
\Lambda^{\max} \ge \lambda_g, \quad \Lambda^{\min} \le \lambda_g \qquad \forall g \in G
$$

$$
P_5 = \Lambda^{\max} - \Lambda^{\min}
$$

$P_5$ là chênh lệch giữa người coi nhiều ca nhất và người coi ít ca nhất. Chỉ tính trên tập $G$ (người tham gia coi thi). Giảng viên bận gần hết đợt thi nên được loại khỏi $G$ ngay từ dữ liệu, nếu không $\Lambda^{\min}$ sẽ bị kéo xuống và mục tiêu này mất ý nghĩa.

#### A-S6. Số lượt thi

Phạt mỗi lượt vượt quá lượt đầu tiên của một môn:

$$
P_6 = \sum_{c \in C} \Big( \sum_{s \in S_c} x_{c,s} - 1 \Big)
$$

Môn thi máy quá đông bắt buộc phải có ít nhất $\lceil n_c / \sum_{r \in R_c} \kappa_r \rceil$ lượt. Phần bắt buộc này cũng bị tính vào $P_6$, nhưng là hằng số với mọi lời giải hợp lệ nên không ảnh hưởng đến việc chọn lời giải.

#### Hàm mục tiêu

$$
\min \ Z = \omega_1 P_1 + \omega_2 P_2 + \omega_3 P_3 + \omega_4 P_4 + \omega_5 P_5 + \omega_6 P_6
$$

Trọng số mặc định. CP-SAT chỉ nhận hệ số nguyên nên mọi trọng số là số nguyên:

| Trọng số | Giá trị | Đơn vị của $P_k$ | Lý do |
|---|---|---|---|
| $\omega_1$ (A-S1) | 100 | Môn thừa trong ngày | Ưu tiên cao nhất về trải nghiệm sinh viên |
| $\omega_2$ (A-S2) | 30 | Môn thừa trong cửa sổ 2 ngày | Quan trọng nhưng kém A-S1 |
| $\omega_3$ (A-S3) | 50 | Phòng thêm | Mỗi phòng thêm tốn 2 giám thị |
| $\omega_4$ (A-S4) | 1 | Chỗ trống × ca | Đơn vị nhỏ nhất, dùng làm mốc |
| $\omega_5$ (A-S5) | 20 | Ca coi thi chênh lệch | |
| $\omega_6$ (A-S6) | 200 | Lượt thêm (đề thêm) | Ra thêm một đề tốn công nhất |

Cách đọc: thêm một lượt (tốn 200) chỉ đáng khi nó giúp ít nhất 2 sinh viên không phải thi 2 môn cùng ngày (tiết kiệm 2 × 100). Một phòng thêm (tốn 50) đáng giá bằng 50 chỗ trống × ca.

Các trọng số này là điểm khởi đầu. Phần thực nghiệm sẽ thay đổi chúng để xem lời giải thay đổi ra sao (phân tích độ nhạy, câu hỏi thứ 5 của Daskin), và có thể vẽ đường cong đánh đổi giữa hai mục tiêu, ví dụ $P_1$ và $P_6$.

### A.7. Chiến lược giải

Mặc định giải toàn bộ mô hình một lần bằng CP-SAT, với giới hạn thời gian (mặc định 300 giây). Kết quả trả về một trong bốn trạng thái:

| Trạng thái CP-SAT | Ý nghĩa với người dùng |
|---|---|
| `OPTIMAL` | Lịch tối ưu theo hàm mục tiêu |
| `FEASIBLE` | Lịch hợp lệ, chưa chứng minh tối ưu (hết thời gian) |
| `INFEASIBLE` | Không tồn tại lịch thỏa mọi ràng buộc cứng; báo nguyên nhân theo A.8 |
| `UNKNOWN` | Hết thời gian mà chưa tìm được lịch hợp lệ nào |

Nếu mô hình đầy đủ chạy quá chậm với bộ `large`, dùng chiến lược hai pha:

1. Pha 1: bỏ biến $w$ và các ràng buộc A-H7, A-H8, A-H10, mục tiêu A-S5. Giữ ràng buộc bổ trợ ở cuối A.5 để đảm bảo mỗi ca không dùng nhiều phòng hơn số giám thị cho phép. Giải tìm lượt, ca, phòng và phân sinh viên.
2. Pha 2: cố định kết quả pha 1, chỉ giải phần giám thị (biến $w$, A-H7, A-H8, A-H10, A-S5). Bài toán này nhỏ và giải rất nhanh.

Hai pha có thể cho lời giải kém hơn giải một lần, vì pha 1 không biết lịch bận của từng giám thị. Nếu pha 2 vô nghiệm (hiếm, chỉ xảy ra khi bật A-H10 hoặc khi ràng buộc giữ nguyên giám thị cho lượt 2 ca không thỏa được), quay lại giải một lần với giới hạn thời gian dài hơn. Khi viết báo cáo, so sánh hai cách này là một phần thực nghiệm tốt.

Kết quả thử ở A.13 cho thấy phần giám thị làm thời gian chứng minh tối ưu tăng rõ rệt, kể cả với dữ liệu rất nhỏ. Lý do là các giám thị rảnh cùng lúc có thể đổi chỗ cho nhau mà không làm thay đổi giá trị mục tiêu, nên solver phải xét rất nhiều lời giải tương đương. Vì vậy khi cài đặt cần làm cả hai cách, và dự kiến dùng hai pha làm mặc định cho bộ `medium` và `large`. Quyết định cuối cùng dựa trên số đo thực nghiệm.

### A.8. Kiểm tra dữ liệu trước khi giải

Các kiểm tra sau chạy trước khi dựng mô hình. Mỗi lỗi được báo bằng một thông điệp chỉ rõ đối tượng gây lỗi.

| Mã | Điều kiện lỗi | Mức độ |
|---|---|---|
| P1 | Có môn $\tau_c > 280$ | Lỗi, dừng |
| P2 | Có môn $n_c = 0$ | Cảnh báo, bỏ môn đó khỏi mô hình |
| P3 | Có môn $R_c = \emptyset$ (ví dụ thi máy nhưng khoa không có phòng máy) | Lỗi, dừng |
| P4 | Có môn $S_c = \emptyset$ | Lỗi, dừng |
| P5 | Có môn $n_c > L_c \cdot \sum_{r \in R_c} \kappa_r$ (kể cả dùng hết phòng ở mọi lượt vẫn không đủ chỗ) | Lỗi, dừng |
| P6 | $\lvert G \rvert < \nu$ | Lỗi, dừng |
| P7 | Môn thi viết có $L_c \ge 2$ | Thông tin: môn này được phép chia lượt theo dữ liệu |
| P8 | Có cặp (sinh viên, môn) bị lặp trong dữ liệu đăng ký | Cảnh báo, loại bản ghi trùng |
| P9 | Có phòng $\kappa_r \le 0$ | Cảnh báo, loại phòng đó khỏi mô hình |

Các kiểm tra này là điều kiện cần, không phải điều kiện đủ. Dữ liệu qua hết các kiểm tra vẫn có thể vô nghiệm, ví dụ khi có quá nhiều môn trùng sinh viên so với số ca. Khi đó CP-SAT trả về `INFEASIBLE`. Để gợi ý nguyên nhân, chạy lại lần lượt với một nhóm ràng buộc được nới ra (ví dụ bỏ phần giám thị, rồi bỏ A-H2) và báo nhóm nào làm mô hình có nghiệm trở lại.

### A.9. Đối chiếu với 10 quy tắc lập mô hình của Daskin

| Quy tắc | Áp dụng trong mô hình |
|---|---|
| 1. Định nghĩa rõ mọi tập hợp bằng lời | Bảng A.2 |
| 2. Tách bạch tập hợp, đầu vào, biến quyết định | Ba bảng riêng A.2, A.3, A.4 |
| 3. Có chỉ số trong ký hiệu thì có trong lời định nghĩa | Mọi ký hiệu có chỉ số đều nêu chỉ số trong cột ý nghĩa |
| 4. Không để chỉ số lơ lửng trong hàm mục tiêu | Mọi chỉ số trong $P_1, \dots, P_6$ đều nằm dưới một dấu tổng |
| 5. Mục tiêu và mỗi ràng buộc chứa biến quyết định | Đã kiểm tra từng công thức |
| 6. Mọi nhóm biến phải liên kết với nhau | $u \le x$; $q \le x$ và $x \le \sum q$; $w$ nối với $u$ qua $o_{r,t}$ (A-H7) |
| 7. Mỗi chỉ số hoặc lấy tổng hoặc "với mọi", không cả hai | Đã kiểm tra từng công thức |
| 8. Giữ mô hình tuyến tính | Mọi ràng buộc tuyến tính; không có tích hai biến nhờ biến $q_{i,c,s}$ gắn trực tiếp với ca bắt đầu |
| 9. Tránh big-M | Không dùng; ràng buộc giữ nguyên giám thị ở A-H7 chỉ dùng hằng số 1 |
| 10. Tách nhỏ ràng buộc | $u_{c,r,s} \le x_{c,s}$ và $q_{i,c,s} \le x_{c,s}$ viết cho từng phần tử thay vì gộp |

### A.10. Hậu xử lý

Sau khi có lời giải:

1. Chia sinh viên của mỗi lượt vào từng phòng của lượt đó, theo thứ tự mã sinh viên, lấp đầy phòng lớn trước. Luôn làm được vì tổng sức chứa đã đủ (A-H3).
2. Ghép mỗi phòng với hai giám thị đã được xếp.
3. Tính KPI theo định nghĩa trong scope (mục 7).
4. Chạy validator: một chương trình độc lập với solver, kiểm tra lại từng ràng buộc cứng trên lời giải cuối cùng và báo vi phạm theo mã.

### A.11. Kích thước mô hình ước lượng

Ước lượng giới hạn trên, với 48 ca, giả sử mỗi sinh viên học 4–5 môn, 1/3 số môn thi trên máy và được chia lượt:

| Bộ dữ liệu | Môn | Phòng | Sinh viên | Giám thị | Biến nhị phân (xấp xỉ) | Ràng buộc A-H2 |
|---|---|---|---|---|---|---|
| `toy` | 5 | 3 | 50 | 6 | 3 nghìn | 2,4 nghìn |
| `medium` | 30 | 10 | 500 | 25 | 55 nghìn | 24 nghìn |
| `large` | 60 | 15 | 1.000 | 40 | 140 nghìn | 48 nghìn |

Phần lớn biến đến từ $q$ (phân sinh viên vào lượt) và $w$ (giám thị). Các cách thu nhỏ mô hình khi cài đặt, không làm thay đổi tập nghiệm:

- Không tạo biến cho ca phòng bận và ca giám thị bận (A-H6, A-H8).
- Với sinh viên chỉ học các môn không chia lượt, nhiều sinh viên có cùng tập môn sẽ sinh ra những ràng buộc A-H2 giống hệt nhau; chỉ cần giữ một bản.
- Dùng chiến lược hai pha ở A.7.

### A.12. Những điều mô hình cố ý không xét

Để tránh hiểu lầm khi đọc kết quả:

- Không xếp chỗ ngồi cụ thể trong phòng; chỉ chia sinh viên vào phòng ở bước hậu xử lý.
- Không giới hạn số ca coi thi tối đa của một giám thị trong một ngày; chỉ cân bằng tổng số ca (A-S5).
- Không xét quãng đường di chuyển giữa các tòa nhà.
- Giả định mỗi lượt của môn chia lượt có đề riêng; việc ra đề nằm ngoài hệ thống.
- Không xét nguyện vọng ngày thi của sinh viên.

### A.13. Kiểm chứng đặc tả

Đặc tả này đã được kiểm chứng bằng một bản cài đặt thử với OR-Tools CP-SAT 9.15, viết đúng theo các công thức A.4 đến A.6, cùng một bộ kiểm tra viết độc lập. Bộ kiểm tra không dùng lại công thức của mô hình mà soát lời giải trực tiếp theo luật trong `scope.md`, tính bằng giờ đồng hồ thật của từng ca.

Dữ liệu thử: 4 ngày, 15 ca (một ca nghỉ giữa buổi sáng), 3 phòng (2 thường, 1 máy), 30 sinh viên, 6 giám thị, 5 môn gồm: môn thi viết cần 2 phòng, môn thi viết 180 phút (2 ca), môn thi máy 20 sinh viên trên phòng 8 máy (buộc chia ít nhất 3 lượt), môn thi máy 150 phút buộc chia lượt, môn thi viết được phép chia lượt. Có phòng bận và giám thị bận.

| Kịch bản | Kết quả mong đợi | Kết quả |
|---|---|---|
| Dữ liệu chuẩn, A-H10 tắt và bật | Có lời giải, không vi phạm | Tối ưu, không vi phạm; điểm phạt tính lại độc lập khớp với solver |
| Môn thi máy 20 sinh viên nhưng chỉ cho 1 lượt | Vô nghiệm | `INFEASIBLE` |
| Chỉ còn 1 giám thị | Vô nghiệm | `INFEASIBLE` |
| 8 bộ dữ liệu ngẫu nhiên × 2 trạng thái A-H10 | Không vi phạm | 16/16 không vi phạm |
| Cố ý làm hỏng lời giải theo 8 cách (bỏ lượt, sai ca 2 ca, sai loại phòng, thiếu chỗ, trùng lượt, trùng ca, thiếu giám thị, giám thị coi môn mình dạy) | Bộ kiểm tra phải phát hiện | 8/8 phát hiện đúng mã lỗi |

Thời gian chứng minh tối ưu trên dữ liệu thử: 20 đến 56 giây tùy biến thể; bỏ mục tiêu A-S5 nhanh hơn. Đây là cơ sở cho khuyến nghị dùng hai pha ở A.7.

---

## B. Bài toán lịch phòng học/phòng máy

Sẽ bổ sung ở phiên bản sau.
