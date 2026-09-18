-- =========================================================
-- announcements(공고) 중 마감일이 있는 데이터를
-- calendar_events(POLICY 타입)로 옮겨 넣는 스크립트
--
-- 실행 시점: policies + announcements 데이터가 이미 다 채워진 뒤 (한 번, 또는 데이터가 갱신될 때마다)
-- 실행 방법: DBeaver에서 열어서 전체 실행, 또는
--            docker exec -i startup_db psql -U admin -d startup_platform < DB/scripts/link_policy_calendar.sql
--
-- 마감일(apply_end_date)이 없는 공고("상시접수" 등)는 제외
-- 이미 들어간 것과 중복되면 자동으로 스킵
-- =========================================================

INSERT INTO calendar_events (event_type, policy_id, title, due_date, description)
SELECT
    'POLICY',
    a.policy_id,
    p.title,
    a.apply_end_date,
    '신청 마감일: ' || a.apply_end_date
FROM announcements a
JOIN policies p ON a.policy_id = p.id
WHERE a.apply_end_date IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM calendar_events c
      WHERE c.policy_id = a.policy_id
        AND c.due_date = a.apply_end_date
        AND c.event_type = 'POLICY'
  );