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

---

## 🔲 예정

### 3. Node/Job 상태 색상 구분
- **설명**: Job/Node 상태에 따라 색상 표시
- **구현 방법**:
  - RUNNING: 녹색
  - PENDING: 노란색
  - COMPLETED: 회색
  - FAILED/CANCELLED: 빨간색
  - Node idle: 녹색, alloc: 노란색, down: 빨간색
- **파일**: `app.py` - `_populate_jobs()`, `_populate_nodes()` 메서드
- **난이도**: 쉬움

### 4. 탭 전환 단축키
- **설명**: 숫자키로 탭 빠르게 전환
- **구현 방법**:
  - `1`: Jobs 탭
  - `2`: Nodes 탭 (또는 Script)
  - Binding 추가 및 action 메서드 구현
- **파일**: `app.py` - BINDINGS 및 action 메서드
- **난이도**: 쉬움

### 5. 필터 UI 개선
- **설명**: 상태별/사용자별 필터를 UI로 제공
- **구현 방법**:
  - Select 위젯으로 상태 필터 (ALL, RUNNING, PENDING, COMPLETED)
  - Input 위젯으로 사용자 필터
  - 필터 초기화 버튼
- **파일**: `app.py`, `widgets.py`
- **난이도**: 중간

### 6. Job 취소 기능
- **설명**: 선택된 Job을 취소 (scancel)
- **구현 방법**:
  - `c` 또는 `Delete` 키로 취소
  - 확인 다이얼로그 표시
  - `scancel {jobid}` 실행
- **파일**: `app.py`, `slurm_client.py`
- **난이도**: 중간

### 7. GPU 사용량 시각화
- **설명**: GPU 사용량을 progress bar로 표시
- **구현 방법**:
  - Rich의 Progress bar 또는 Text로 시각화
  - `[████░░░░] 4/8` 형태
- **파일**: `app.py` - `_populate_nodes()`
- **난이도**: 중간

### 8. 실행 시간 비율 표시
- **설명**: 실행 시간 / 제한 시간 비율 표시
- **구현 방법**:
  - TimeUsed와 TimeLimit 파싱
  - 비율 계산 및 색상 표시 (80% 이상 노란색, 95% 이상 빨간색)
- **파일**: `app.py`, `slurm_client.py`
- **난이도**: 중간

### 9. 새로고침 개선
- **설명**: 새로고침 상태 및 간격 조정
- **구현 방법**:
  - StatusBar에 마지막 새로고침 시간 표시
  - `+`/`-` 키로 새로고침 간격 조정
  - 새로고침 중 로딩 표시
- **파일**: `app.py`, `widgets.py`
- **난이도**: 쉬움

### 10. Job 정보 복사
- **설명**: 선택된 Job 정보를 클립보드에 복사
- **구현 방법**:
  - `y` 키로 Job ID 복사
  - `Y` 키로 전체 Job 정보 복사
  - pyperclip 또는 시스템 명령어 사용
- **파일**: `app.py`
- **난이도**: 쉬움

### 11. 컬럼 정렬
- **설명**: 테이블 컬럼 클릭 시 정렬
- **구현 방법**:
  - DataTable의 sort 기능 활용
  - 정렬 상태 아이콘 표시 (▲/▼)
- **파일**: `app.py`
- **난이도**: 중간

### 12. 설정 저장
- **설명**: 사용자 설정을 파일로 저장
- **구현 방법**:
  - `~/.config/smon/config.json` 에 저장
  - 새로고침 간격, 필터, 레이아웃 등
- **파일**: 새 파일 `config.py`
- **난이도**: 중간

### 13. 테마 토글
- **설명**: 다크/라이트 테마 전환
- **구현 방법**:
  - Textual의 테마 기능 활용
  - `T` 키로 토글
- **파일**: `app.py`, `styles.py`
- **난이도**: 쉬움

