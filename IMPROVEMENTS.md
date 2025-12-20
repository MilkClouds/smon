# smon 개선사항 스펙

## ✅ 완료

### 1. Job List 스크롤 추가 ✓
- DataTable을 ScrollableContainer로 감싸서 스크롤 가능하게
- Jobs 탭과 Nodes 탭 모두 적용
- 파일: `app.py`, `styles.py`

### 2. Split View 레이아웃 ✓
- Job 선택 시 오른쪽 패널에 Job Detail + Script + Output 동시 표시
- 탭 구조 간소화: Jobs | Nodes (기존 Script/Output 탭 제거)
- STDOUT/STDERR을 나란히 표시
- 파일: `app.py`, `styles.py`

### 3. Node/Job 상태 색상 구분 ✓
- Job/Node 상태에 따라 색상 표시
- RUNNING: 녹색, PENDING: 노란색, COMPLETED: 회색, FAILED/CANCELLED: 빨간색
- Node idle: 녹색, alloc: 노란색, down: 빨간색
- 파일: `app.py` - `_format_state()`, `JOB_STATE_COLORS`, `NODE_STATE_COLORS`

### 4. 탭 전환 단축키 ✓
- `1`: Jobs 탭, `2`: Nodes 탭
- 파일: `app.py` - `action_goto_jobs()`, `action_goto_nodes()`

### 5. Job 취소 기능 ✓
- `c` 키로 취소 (2번 누르면 확인)
- 파일: `app.py`, `slurm_client.py` - `cancel_job()`

### 6. GPU 사용량 시각화 ✓
- GPU 사용량을 progress bar로 표시 (`████░░░░ 4/8` 형태)
- 파일: `app.py` - `_format_gpu_bar()`

### 7. 실행 시간 비율 표시 ✓
- TimeUsed / TimeLimit 비율 계산 및 색상 표시
- 80% 이상: 노란색, 95% 이상: 빨간색
- 파일: `app.py`, `slurm_client.py` - `parse_time_to_seconds()`, `calculate_time_ratio()`

### 8. 새로고침 개선 ✓
- StatusBar에 마지막 새로고침 시간 및 간격 표시
- `+`/`-` 키로 새로고침 간격 조정 (1초~60초)
- 파일: `app.py` - `action_increase_refresh()`, `action_decrease_refresh()`

### 9. Job 정보 복사 ✓
- `y` 키로 Job ID 복사 (xclip/xsel/pbcopy 사용)
- 파일: `app.py` - `action_copy_jobid()`

### 10. 컬럼 정렬 ✓
- 테이블 컬럼 클릭 시 정렬
- 정렬 상태 표시 (▲/▼)
- 파일: `app.py` - `on_data_table_header_selected()`

### 11. 필터 UI 개선 ✓
- Select 위젯으로 상태 필터 (All States, Running, Pending, Completed, Failed, Cancelled)
- 파일: `app.py` - `STATE_OPTIONS`, `on_select_changed()`, `styles.py` - `.filter-bar`, `.state-select`

### 12. 설정 저장 ✓
- `~/.config/smon/config.json`에 설정 저장/로드
- 파일: `config.py` - `Config` 클래스

### 13. 테마 토글 ✓
- `T` 키로 다크/라이트 테마 전환
- 파일: `app.py` - `action_toggle_theme()`

---

## ✅ 모든 개선사항 완료!

