import React, { useEffect, useState } from 'react';
import { GuideTour } from './GuideTour.jsx';

// 기능 페이지별 화면 안내. 페이지에 처음 들어왔을 때 한 번만 자동으로 띄우고,
// 이후에는 오른쪽 아래 '?' 버튼으로만 연다. 대상이 없는 항목(예: 영수증이 없을 때의 목록)은 건너뛴다.
const HELP = {
  target: '.tour-fab',
  title: '가이드 다시 보기',
  body: <p>사용법이 궁금하면 언제든 이 버튼을 눌러 안내를 다시 볼 수 있어요.</p>,
};

export const PAGE_TOURS = {
  roadmap: {
    label: '창업 로드맵 가이드',
    steps: [
      {
        target: '.rz',
        title: '창업 7단계',
        body: <p>아이디어 검증부터 스케일업까지 창업 과정을 7단계로 나눴어요. 단계를 누르면 그 단계에서 할 일로 바뀌어요.</p>,
      },
      {
        target: '.rg2__prog',
        title: '전체 진행률',
        body: <p>완료한 작업 수로 진행률을 계산해요. 진행 상황은 마이페이지 대시보드에서도 볼 수 있어요.</p>,
      },
      {
        target: '.rg2__goal',
        title: '이 단계의 목표',
        body: <p>지금 단계에서 무엇을 이루면 되는지 한 줄로 정리했어요.</p>,
      },
      {
        target: '.rg2__tasks',
        title: '할 일 체크리스트',
        body: <p>끝낸 일은 체크해 주세요. 항목을 누르면 방법과 근거를 볼 수 있고, '놓치면 손해' 표시는 기한을 넘기면 불이익이 있는 일이에요.</p>,
      },
      {
        target: '.rg2__chat',
        title: '로드맵 AI 코치',
        body: <p>지금 단계에서 막히는 점이나 준비할 것을 물어보세요.</p>,
      },
      HELP,
    ],
  },
  gov: {
    label: '공고지원 AI 가이드',
    steps: [
      {
        target: '.az2__card',
        title: '추천 공고',
        body: <p>내 사업자 정보에 맞는 지원사업을 적합도 순으로 모았어요. 오른쪽의 D-day로 마감까지 남은 날을 확인하세요.</p>,
      },
      {
        target: '.az2__recactions',
        title: '공고 보기·저장',
        body: <p>'상세 보기'는 공고의 핵심 내용을 정리해 보여주고, '원문 확인하기'는 공고 원문으로 연결해요. 저장한 공고는 마이페이지에 모여요.</p>,
      },
      {
        target: '.cal',
        title: '창업 일정',
        body: <p>이번 달 세금 신고와 지원사업 마감 일정이에요. 일정 추가와 전체 일정은 마이페이지에서 관리해요.</p>,
      },
      {
        target: '.az2__chat',
        title: '공고 상담',
        body: <p>지원 자격, 필요한 서류, 사업계획서 방향을 물어보세요. 예시 질문을 누르면 바로 시작할 수 있어요.</p>,
      },
      HELP,
    ],
  },
  tax: {
    label: 'AI 세무 Assistant 가이드',
    steps: [
      {
        target: '.cvx__main',
        title: 'AI 세무 상담',
        body: <p>부가세, 종합소득세, 간이·일반과세자 같은 세무 질문에 세법 자료를 찾아 답해 줘요. 신고 전 최종 판단은 세무사와 확인하세요.</p>,
      },
      {
        target: '.ai__foot',
        title: '질문 입력',
        body: <p>궁금한 점을 문장으로 적고 전송하세요. 이어서 질문하면 앞의 대화를 이어받아 답해요.</p>,
      },
      {
        target: '.cvx__new',
        title: '새 대화 시작',
        body: <p>주제가 바뀌면 새 대화를 여세요. 앞의 대화와 섞이지 않아 답이 더 정확해져요.</p>,
      },
      {
        target: '.cvx__list',
        title: '이전 대화',
        body: <p>지난 상담은 날짜별로 저장돼요. 눌러서 다시 보거나 이름을 바꾸고 지울 수 있어요.</p>,
      },
      HELP,
    ],
  },
  expenses: {
    label: '지출관리 가이드',
    steps: [
      {
        target: '.exp-drop',
        title: '영수증 올리기',
        body: <p>영수증 사진을 끌어다 놓거나 눌러서 고르세요. 여러 장을 한 번에 올릴 수 있고, AI가 상호·금액·품목·증빙 종류를 읽어 경비 인정 가능성을 판정해요.</p>,
      },
      {
        target: '.exp-rate',
        title: '이번 달 인정률',
        body: <p>이번 달 영수증 중 경비로 인정될 가능성이 높은 비율이에요.</p>,
      },
      {
        target: '.exp-filter',
        title: '판정별 보기',
        body: <p>인정·확인 필요·불인정으로 나눠 볼 수 있어요. '확인 필요'부터 살펴보면 놓치는 경비를 줄일 수 있어요.</p>,
      },
      {
        target: '.exp-row',
        title: '영수증 한 건',
        body: <p>지출항목을 눌러 바꿀 수 있고, 상호 옆 연필로 상호를 고쳐요. 오른쪽 ⋮ 메뉴에서 판독 내용·판단 근거·관련 법령을 보거나 삭제해요.</p>,
      },
      {
        target: '.exp-listhead__search',
        title: '검색',
        body: <p>상호나 지출항목으로 영수증을 찾을 수 있어요.</p>,
      },
      {
        target: '.exp-export',
        title: '엑셀로 내보내기',
        body: <p>지금 보고 있는 목록을 요약·지출 내역·품목 상세 세 시트짜리 엑셀로 내려받아요.</p>,
      },
      HELP,
    ],
  },
  mypage: {
    label: '마이페이지 가이드',
    steps: [
      {
        target: '.mp-dash',
        title: '한눈에 보는 대시보드',
        body: <p>로드맵 진행률, 마감이 임박한 일정, 최근 AI 상담을 모아 보여줘요. 카드의 링크를 누르면 해당 기능으로 이동해요.</p>,
      },
      {
        target: '.cal',
        title: '일정 관리',
        body: <p>날짜를 누르고 일정을 추가하세요. 세금 신고와 지원사업 일정을 색으로 구분해요.</p>,
      },
      {
        target: '.mp-nav',
        title: '내 정보와 저장한 것',
        body: <p>'사업자 정보'를 입력하면 공고 추천과 세무 답변이 내 조건에 맞춰져요. 저장한 공고·정책과 내가 만든 사업계획서(이어서 작성·이름 변경·삭제)도 여기서 관리해요.</p>,
      },
      HELP,
    ],
  },
};

const TOUR_KEY = (userId, page) => `changeup:page-tour:v1:${userId || 'guest'}:${page}`;

// 페이지 안내 + 다시 보기 버튼. 처음 들어왔을 때 한 번만 자동으로 열고, 여는 순간 본 것으로 기록한다.
export function PageTour({ page, userId }) {
  const tour = PAGE_TOURS[page];
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(false);
    // 로그인 전에는 화면 대부분이 로그인 안내라서 자동으로 띄우지 않는다(버튼으로는 볼 수 있다).
    if (!tour || !userId) return undefined;
    const key = TOUR_KEY(userId, page);
    try {
      if (localStorage.getItem(key) === 'done') return undefined;
    } catch (e) {
      // 기록을 남길 수 없으면 들어올 때마다 뜨게 되므로 자동 안내를 하지 않는다.
      return undefined;
    }
    // 목록·일정 같은 데이터가 그려진 뒤에 대상을 고르도록 조금 기다린다.
    const t = setTimeout(() => {
      try {
        localStorage.setItem(key, 'done');
      } catch (e) {
        return;
      }
      setOpen(true);
    }, 900);
    return () => clearTimeout(t);
  }, [page, userId, tour]);

  if (!tour) return null;
  return (
    <React.Fragment>
      <button type="button" className="tour-fab" onClick={() => setOpen(true)}
        aria-label={`${tour.label} 보기`} title="사용 가이드">
        ?
      </button>
      <GuideTour open={open} steps={tour.steps} onClose={() => setOpen(false)} label={tour.label} />
    </React.Fragment>
  );
}
