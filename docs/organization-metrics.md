# Cập nhật số liệu GitHub tổ chức — lowlighter/metrics

## Mục tiêu và giới hạn

- Repository chứa workflow: `tuanchaugroup/.github`, nhánh mặc định `main`.
- Workflow: [`.github/workflows/organization-metrics.yml`](../.github/workflows/organization-metrics.yml).
- Đầu ra: `assets/metrics/organization.svg`, được hiển thị trong `profile/README.md`.
- Chạy hằng ngày lúc **08:17 giờ Việt Nam** (`17 1 * * *` theo UTC), hoặc chạy thủ công bằng `workflow_dispatch`. Lịch có thể chạy trễ do GitHub Actions.
- Phạm vi **chỉ số liệu công khai**. Phần lớn repository của tổ chức là private; đồ thị này không đại diện cho tất cả repository hay hoạt động nhân sự.
- Không đăng công khai thông tin về thành viên, mã nguồn hoặc hoạt động nội bộ của repository private.

## 1. Cấp token bắt buộc

Theo tài liệu chính thức của `lowlighter/metrics`, số liệu tổ chức cần PAT của tài khoản có quyền đọc tổ chức:

1. Dùng một tài khoản được tổ chức cho phép; tạo **Personal Access Token (classic)** chỉ với scope `read:org` (không thêm `repo`, `admin:org` hay quyền ghi).
2. Nếu tổ chức dùng SSO, cấp quyền SSO tương ứng cho token.
3. Vào **tuanchaugroup/.github → Settings → Secrets and variables → Actions → New repository secret**.
4. Đặt tên `METRICS_TOKEN`, dán giá trị PAT. **Không đặt token vào YAML, commit, issue hoặc README.**
5. Dùng thời hạn token phù hợp và có chủ sở hữu/nhắc gia hạn để tránh báo cáo ngừng cập nhật.

`GITHUB_TOKEN` được workflow dùng **riêng để ghi SVG** lên `main` với `contents: write`; nó không thay thế PAT dùng để đọc dữ liệu tổ chức.

**Không dùng PAT có scope `repo` trong workflow public này.** Nếu cần báo cáo cả repo private, hãy tạo quy trình và đích xuất hoàn toàn **private** được phê duyệt riêng.

## 2. Chạy thử và xác minh

1. Mở tab **Actions → Organization GitHub Metrics → Run workflow** trên nhánh `main`.
2. Xác minh bước `Require METRICS_TOKEN` và `Generate public organization metrics` thành công.
3. Kiểm tra `assets/metrics/organization.svg` đã được action cập nhật và có commit mới.
4. Mở trang [GitHub tổ chức Tuần Châu Group](https://github.com/tuanchaugroup); tải lại để xác nhận hình được hiển thị.
5. Xem lịch sử workflow để kiểm tra lần cập nhật gần nhất; nếu thiếu cập nhật, xem log của Actions.

## 3. Quyền và bảo mật

- Workflow chỉ cấp `contents: write` cho `GITHUB_TOKEN` để commit SVG.
- PAT với `read:org` là bí mật; GitHub chỉ cung cấp qua secret.
- File kết quả được lưu trong repo public nên có thể xem và tải bởi bất kỳ ai.
- Action được **pin theo commit SHA**, tránh tự đổi phiên bản theo tag; cập nhật action bằng PR, review và kiểm thử.
- Nếu nhánh `main` có branch protection/ruleset cấm GitHub Actions ghi trực tiếp, bước commit có thể thất bại; cần thiết kế PR-based output hoặc cấp quyền theo chính sách, không tắt bảo vệ nhánh tùy tiện.
- Không chỉnh sửa `.github/workflows/snake.yml`: workflow metrics chỉ ghi `main`, workflow snake đang xuất vào nhánh `output`.

## 4. Xử lý sự cố

| Hiện tượng | Cách kiểm tra |
|---|---|
| `METRICS_TOKEN missing` | Tạo secret ở repository `.github`; kiểm tra tên chính xác |
| HTTP 401/403 | Kiểm tra PAT còn hạn, quyền `read:org`, SSO và quyền tổ chức |
| Không ghi được SVG | Xem `contents: write`, Actions workflow permissions, branch protection |
| Ảnh chưa cập nhật trong profile | Kiểm tra file SVG trên nhánh `main`, cache của GitHub và trạng thái workflow |
| Lịch không chạy | GitHub có thể trì hoãn hoặc vô hiệu hóa workflow theo chính sách; dùng chạy thủ công để kiểm chứng |
| Chỉ có rất ít dữ liệu | Đúng với cấu hình chỉ hiển thị repository công khai; không nâng quyền token một cách tùy tiện |

## Tài liệu tham khảo

- https://github.com/lowlighter/metrics/blob/master/.github/readme/partials/documentation/organizations.md
- https://github.com/lowlighter/metrics/blob/master/.github/readme/partials/documentation/setup/action.md
- https://github.com/lowlighter/metrics/blob/master/source/plugins/base/README.md
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
