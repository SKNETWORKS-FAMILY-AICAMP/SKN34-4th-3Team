-- =========================================================
-- policies.region 지역명 정규화 스크립트
--
-- 기존에 적재된 데이터 업데이트용
-- =========================================================
UPDATE policies
SET region = '전국'
WHERE region IS NOT NULL
  AND length(region) >= 1500;

UPDATE policies
SET region = CASE
    WHEN region IN ('서울', '서울시', '서울특별시') THEN '서울'
    WHEN region IN ('부산', '부산시', '부산광역시') THEN '부산'
    WHEN region IN ('대구', '대구시', '대구광역시') THEN '대구'
    WHEN region IN ('인천', '인천시', '인천광역시') THEN '인천'
    WHEN region IN ('광주', '광주시', '광주광역시', '전남광주', '전남광주통합특별시') THEN '광주'
    WHEN region IN ('대전', '대전시', '대전광역시') THEN '대전'
    WHEN region IN ('울산', '울산시', '울산광역시') THEN '울산'
    WHEN region IN ('세종', '세종시', '세종특별자치시') THEN '세종'
    WHEN region IN ('경기', '경기도') THEN '경기'
    WHEN region IN ('강원', '강원도', '강원특별자치도') THEN '강원'
    WHEN region IN ('충북', '충청북도') THEN '충북'
    WHEN region IN ('충남', '충청남도') THEN '충남'
    WHEN region IN ('전북', '전라북도', '전북특별자치도') THEN '전북'
    WHEN region IN ('전남', '전라남도') THEN '전남'
    WHEN region IN ('경북', '경상북도') THEN '경북'
    WHEN region IN ('경남', '경상남도') THEN '경남'
    WHEN region IN ('제주', '제주도', '제주특별자치도') THEN '제주'
    WHEN region IN (
        '서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종',
        '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'
    ) THEN region
    ELSE region
END
WHERE region IS NOT NULL
  AND region != '전국';