// 布可找書 V3: 純資料判斷層，尚未連線任何即時館藏 API。
// 請只把有明確外借資格的冊數列為「可借」，勿因「在架」就推定可外借。
// Input example:
// { isbn, checkedAt, source:'authorized-api', copies:[
//   {barcode, homeLibrary, currentLibrary, shelfLocation, status:'在架', borrowable:true, reservationCount:0}
// ] }
const NON_CIRCULATING = /不外借|限館內閱覽|僅限館內|館內閱覽|參考資料區|參考書區|中文參考書|參考工具書/;
const EXHIBITION_BORROWABLE = /^展覽用書\s*[（(]\s*可外借\s*[）)]/;
const ON_SHELF = /^在架(?:\s|$|[（(])|^展覽用書\s*[（(]\s*可外借\s*[）)]/;
const ACCESS_UNAVAILABLE = /閉館整修|浮動館藏區|罕用書庫|線上調閱|移送中/;

export function classifyCopy(copy) {
  const status = String(copy?.status ?? '').trim();
  const shelfLocation = String(copy?.shelfLocation ?? '').trim();
  const homeLibrary = String(copy?.homeLibrary ?? '').trim();
  const currentLibrary = String(copy?.currentLibrary ?? '').trim();
  const restriction = NON_CIRCULATING.test([status, shelfLocation, homeLibrary, currentLibrary, copy?.circulationPolicy ?? '', copy?.dataType ?? ''].join(' '));
  const explicitEligibility = copy?.borrowable === true || copy?.borrowable === false || EXHIBITION_BORROWABLE.test(status);
  const canBorrow = !restriction && (copy?.borrowable === true || (copy?.borrowable == null && EXHIBITION_BORROWABLE.test(status)));
  const onShelf = ON_SHELF.test(status);
  const accessUnavailable = ACCESS_UNAVAILABLE.test([homeLibrary,currentLibrary,shelfLocation].join(' '));
  const reservationCount = Number.isInteger(copy?.reservationCount) && copy.reservationCount >= 0
    ? copy.reservationCount : null;
  return {
    barcode: String(copy?.barcode ?? ''),
    homeLibrary,
    currentLibrary,
    status,
    shelfLocation,
    reservationCount,
    nonCirculating: restriction || copy?.borrowable === false,
    canBorrow,
    canBorrowConfirmed: explicitEligibility || restriction,
    accessUnavailable,
    availableToBorrow: canBorrow && onShelf && !accessUnavailable,
    inLibraryReading: restriction && (onShelf || /展覽用書/.test(status)) && !accessUnavailable,
    potentiallyBorrowableButUnverified: !restriction && !explicitEligibility,
  };
}

export function summarizeHoldings(record, { now = new Date(), maxAgeMinutes = 30 } = {}) {
  const copies = Array.isArray(record?.copies) ? record.copies.map(classifyCopy) : [];
  const borrowable = copies.filter(c => c.canBorrow);
  const available = borrowable.filter(c => c.availableToBorrow);
  const reading = copies.filter(c => c.inLibraryReading);
  const reservationCounts = borrowable.map(c => c.reservationCount).filter(v => v !== null);
  const checkedAt = typeof record?.checkedAt === 'string' ? record.checkedAt : '';
  const checkedTime = Date.parse(checkedAt);
  const nowTime = now instanceof Date ? now.getTime() : Date.parse(now);
  const validAge = Number.isFinite(checkedTime) && Number.isFinite(nowTime)
    && nowTime >= checkedTime && (nowTime - checkedTime <= maxAgeMinutes * 60000);
  const source = String(record?.source ?? 'unknown');
  // 一般公開網頁的人工紀錄只能叫「觀察結果」，不能標成即時可借。
  const liveVerified = source === 'authorized-api' && validAge && record?.complete !== false;
  const unverifiedCopyCount = copies.filter(c => c.potentiallyBorrowableButUnverified).length;
  let observedStatus = 'unknown';
  if (available.length > 0) observedStatus = 'available';
  else if (borrowable.length > 0) observedStatus = 'waiting';
  else if (reading.length > 0 && unverifiedCopyCount === 0 && record?.complete !== false) observedStatus = 'in_library_only';
  // 單一館藏頁往往只包含全市一部分的冊數；不能據此宣稱全市「只剩展示本」。
  if (record?.complete === false && observedStatus === 'waiting') observedStatus = 'unknown';
  // 不可外借和一般在架副本同時存在，應以可借副本為準.
  // 有未確認可借資格的複本時，不得宣稱全市「僅館內閱讀」。
  return {
    isbn: String(record?.isbn ?? ''),
    checkedAt,
    source,
    liveVerified,
    status: validAge ? observedStatus : 'needs_refresh',
    observedStatus,
    complete: record?.complete === true ? true : record?.complete === false ? false : null,
    totalCopies: copies.length,
    availableBorrowableCopies: available.length,
    borrowableCopyCount: borrowable.length,
    inLibraryReadingCopies: reading.length,
    unverifiedCopyCount,
    minReservationCount: reservationCounts.length ? Math.min(...reservationCounts) : null,
    availableLibraries: [...new Set(available.map(c => c.currentLibrary || c.homeLibrary).filter(Boolean))],
    copies,
  };
}
