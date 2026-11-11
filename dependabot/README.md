# TCG Group Dependabot – chính sách và triển khai liên repository

> **Trạng thái:** Chính sách chuẩn được lưu tại repository `tuanchaugroup/.github`. **Chưa tự động áp dụng cho các repository khác** cho tới khi cấu hình được đưa vào `.github/dependabot.yml` trên nhánh mặc định của từng repository. Cập nhật ngày 11/11/2026.

## 1. Điểm cần hiểu đúng

GitHub **không kế thừa** `.github/dependabot.yml` từ repository tên `.github` sang toàn bộ repository trong tổ chức. Khác với một số mẫu cộng đồng như `PULL_REQUEST_TEMPLATE`, Dependabot yêu cầu **file riêng tại `.github/dependabot.yml` (hoặc `.yaml`) trong nhánh mặc định của từng repository**. Tham khảo:

- [About the dependabot.yml file](https://docs.github.com/en/code-security/concepts/supply-chain-security/about-the-dependabot-yml-file)
- [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- [Supported ecosystems and repositories](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories)

File [`.github/dependabot.yml`](../.github/dependabot.yml) tại repository này chỉ theo dõi GitHub Actions của **chính repository `.github`**.

## 2. Chính sách chung

| Thành phần | Quy tắc |
| --- | --- |
| Manifest | Chỉ cấu hình ecosystem có manifest được phát hiện trên **nhánh mặc định thực tế** của repository |
| Lịch | Thứ Ba, 09:00, múi giờ `Asia/Ho_Chi_Minh`, hàng tuần |
| PR | Tối đa 3 PR cập nhật phiên bản đang mở **trên từng ecosystem**; security PR có giới hạn riêng của GitHub |
| Nhóm | Nhóm bản vá `patch` cho npm, NuGet, pip, Cargo, pub; các cập nhật khác tạo PR độc lập để review |
| Major update | **Không tự merge**; không chặn major trong Dependabot config để tránh vô tình loại cả bản sửa lỗi bảo mật |
| Môi trường | PR phải chạy CI, kiểm thử hồi quy và được chủ hệ thống review trước merge; không tự triển khai production |
| Quyền | Không gắn token/password vào YAML; kiểm soát bằng GitHub App hoặc PAT quyền tối thiểu |
| Nhánh | File và PR Dependabot theo **default branch** của từng repo (`main`, `master` hoặc `developer`), không đoán nhánh |
| Cấu hình sẵn có | **Không ghi đè** `.github/dependabot.yml`/`.yaml` nếu đã tồn tại; cần owner xem và hợp nhất bằng PR riêng |

## 3. Phạm vi công nghệ được phát hiện tự động

`sync_dependabot.py` quét **các manifest thực tế** (không chèn một config lớn không có giá trị vào mọi repo):

- .NET: `*.csproj`, `*.fsproj`, `*.vbproj`, `Directory.Packages.props`, `global.json` → `nuget`, `dotnet-sdk`.
- React/Next.js/Vite/Node: `package.json`, các package manager tương thích → `npm`; `bun.lock` → `bun`.
- Python: `pyproject.toml`, `requirements*.txt`, `Pipfile`, Poetry hoặc `uv.lock` → `pip`/`uv`.
- Flutter: `pubspec.yaml` → `pub`; Android Gradle → `gradle`.
- Tauri/Rust: `Cargo.toml` → `cargo`, `rust-toolchain` nếu có.
- Container: `Dockerfile*`, Compose YAML → `docker`, `docker-compose`.
- Khác nếu có: `gomod`, `maven`, `composer`, `terraform`, `helm`, `pre-commit`, `devcontainers` và GitHub Actions.

Bỏ qua các thư mục `node_modules`, `vendor`, `public`, `wwwroot`, `dist`, `build`, file từ AI agent skills, mã phụ thuộc có sẵn và tài nguyên kiểm thử mẫu. **Lưu ý:** các quy tắc loại trừ này cần review theo repo nếu có ứng dụng thực nằm trong một thư mục cùng tên.

## 4. Cách dùng an toàn (chạy từ máy quản trị được ủy quyền)

Yêu cầu: Python 3.10+; token GitHub có **quyền đọc repository private**. Khi áp dụng cần thêm quyền `Contents: write` và `Pull requests: write` trên các repo đích. Không đưa token vào source, logs hoặc repository này.

```bash
# Nạp GITHUB_TOKEN từ hệ thống quản lý bí mật nội bộ; không lưu token trong shell history.
# Chạy thử: chỉ đọc và hiển thị kế hoạch (MẶC ĐỊNH)
python3 dependabot/sync_dependabot.py --org tuanchaugroup

# Thử trên một repository được chỉ định, vẫn chỉ đọc
python3 dependabot/sync_dependabot.py --repo TEN_REPOSITORY

# Mở draft PR trên MỘT repo sau khi kiểm tra kết quả dry-run
python3 dependabot/sync_dependabot.py --repo TEN_REPOSITORY --apply

# Mở draft PR với toàn bộ repo khả dụng đã kiểm kê (CHỈ sau khi người phụ trách phê duyệt)
python3 dependabot/sync_dependabot.py --apply
```

Quy trình mỗi repo: xác định default branch → kiểm tra có config sẵn chưa → quét tree → xác định ecosystem và các thư mục manifest → tạo YAML → **dry-run** hoặc tạo branch `automation/dependabot-policy-v1` + draft PR; **không auto-merge, không force push, không đụng production**.

**An toàn khi chạy lại:** Nếu đã có file Dependabot hoặc branch rollout trùng tên, script **bỏ qua** thay vì ghi đè. Nếu GitHub API báo tree bị cắt (`truncated`) hoặc không có manifest, script bỏ qua và yêu cầu xử lý thủ công. Quyền API và điều kiện branch protection có thể khiến việc tạo draft PR thất bại; kiểm tra kết quả từng repository.

**Không cấu hình job quét private repositories trong Actions của repo `.github` public:** logs của workflow public có thể làm lộ tên repo private, manifest và cấu trúc mã nguồn. Chạy tại máy quản trị có quyền, hoặc trong một repository quản trị **private** với GitHub App token có quyền tối thiểu.

## 5. Bước kiểm tra trước khi merge PR tại từng repository

1. Kiểm tra có đúng thư mục manifest cần theo dõi và không quét mã vendored/code sinh tự động.
2. Kiểm tra feed private (ví dụ NuGet nội bộ), quyền truy cập registry, khả năng truy cập từ Dependabot runner. Quản lý secret qua **Dependabot secrets/organization registry settings**, không đưa vào file YAML và không mặc định tin rằng runner truy cập được mạng nội bộ.
3. Kiểm tra CI: restore/build/typecheck/lint/unit/integration tests; với Flutter và Tauri cần test Android/iOS hoặc Rust tương ứng.
4. Đánh giá nâng cấp breaking changes, SDK/runtime, database driver, Docker image, auth, payment, hệ thống quét vé; xác nhận kế hoạch rollback nếu thay đổi rủi ro cao.
5. Review/merge bởi chủ repo. Bật riêng Dependabot alerts, dependency graph và security updates theo chính sách bảo mật tổ chức; `dependabot.yml` **không tự bật** các tính năng này.

## 6. Phạm vi hiệu lực và bằng chứng

Bộ policy và script đã được kiểm thử tĩnh (Python unit tests, kiểm tra YAML đầu ra) và đối chiếu nhóm manifest từ danh mục repo tổ chức. **Không có bằng chứng workflow Dependabot đã chạy, PR cập nhật phiên bản đã thành công hoặc tất cả repo được kích hoạt** chỉ từ việc commit file này.

Kiểm thử tại chỗ:

```bash
python3 -m unittest discover -s dependabot -p 'test_*.py' -v
```

**Lưu ý về tài liệu public:** Repo `.github` là public. Không ghi danh mục các đường dẫn nội bộ, URL private registry, secrets hoặc trạng thái triển khai nội bộ vào repo này.
