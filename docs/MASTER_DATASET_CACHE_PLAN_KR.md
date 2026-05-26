# Master Dataset Cache 최적화 계획

## 1. 개요
현재 `reversal_edge_master_dataset.jsonl` 파일은 크기가 방대하여(수백만 줄 이상), 매번 분석 도구가 전체 파일을 스트리밍으로 읽어 파싱할 때 심각한 속도 저하가 발생합니다.
이를 해결하기 위해 원본 JSONL 데이터의 손실 없이 SQLite 기반의 로컬 캐시 DB를 구축하여 조회 속도와 메모리 효율성을 극대화합니다.

## 2. 목적
- 대용량 백테스트 및 시뮬레이션(Walk-forward, Cost Randomization 등)의 소요 시간 단축.
- 마켓별, 이벤트 타입별 인덱싱을 통한 빠른 필터링 지원.
- 향후 부분 데이터 추출 및 특정 시간대 분석 시 I/O 병목 완화.

## 3. 원칙 및 제한 사항
1. **원본 보존**: 기존 `reversal_edge_master_dataset.jsonl` 원본 파일은 어떠한 경우에도 삭제하거나 덮어쓰지 않습니다.
2. **모든 데이터 보존**: 특정 마켓이나 이벤트 타입(heartbeat 등 포함)을 임의로 누락시키지 않으며, 전체 raw JSON은 텍스트 필드에 보존합니다.
3. **오프라인 동작**: 외부 DB 인스턴스 구축 없이 파이썬 내장 `sqlite3` 모듈만을 이용해 동작해야 합니다.
4. **자동 캐시 갱신**: 분석 도구 실행 시 사람이 매번 수동으로 캐시를 생성할 필요가 없도록, 원본 JSONL의 수정 시간(mtime)과 크기(size)를 확인하여 변경사항이 감지되면 자동으로 캐시를 재생성(rebuild)합니다.

## 4. 데이터베이스 스키마
테이블명: `events`
| 컬럼명 | 타입 | 설명 |
|---|---|---|
| id | INTEGER PK | 자동 증가 고유 식별자 |
| ts | REAL | 정규화된 timestamp (초 단위) |
| market | TEXT | 대상 마켓 (예: KRW-SOL) |
| event_type | TEXT | 원본 이벤트 타입 |
| normalized_event_type | TEXT | 분류 편의를 위한 타입 (orderbook, trade, 기타) |
| source_file | TEXT | 원본 데이터 소스 경로 |
| line_index | INTEGER | 원본 JSONL 내 줄 번호 |
| raw_json | TEXT | 원본 JSON 문자열 |

### 생성 인덱스
- `idx_events_ts`
- `idx_events_market`
- `idx_events_event_type`
- `idx_events_normalized_event_type`
- `idx_events_market_ts`
- `idx_events_type_ts`
- `idx_events_market_type_ts`

### 메타데이터 테이블 (cache_meta)
- `source_path`: 원본 JSONL 파일 경로
- `source_size`: 파일 크기 (바이트)
- `source_mtime`: 최근 수정 시간
- `source_line_count`: 파싱한 전체 라인 수
- `cache_created_at`: 캐시 생성 시각
- `cache_version`: 캐시 스키마 버전

## 5. 자동 검증 및 연동 방침 (Cache Manager)
- `tools/cache_manager.py`가 실행 시마다 SQLite 캐시의 `cache_meta`와 현재 `master_dataset.jsonl`의 상태(크기, 수정시간 등)를 비교합니다.
- 변경이 없으면 즉시 기존 SQLite 캐시를 재사용하여 속도를 극대화합니다.
- 크기나 수정시간이 달라졌거나 SQLite 파일이 없다면 백그라운드에서 `build_master_dataset_cache.py --rebuild`를 자동 호출하여 최신화합니다.
- Walk-forward Validation, Cost Randomization Test 등 분석 스크립트들은 `cache_manager.ensure_cache()`를 통해 위 과정을 자동으로 수행합니다.
- 분석 결과 보고서(Summary)에 캐시 정상 여부, 자동 재생성 여부를 기록하여 투명성을 유지합니다.
