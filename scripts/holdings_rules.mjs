// 布可找書 V3: 純資料判斷層，尚未連線任何即時館藏 API。
// 請只把有明確外借資格的冊數列為「可借」，勿因「在架」就推定可外借。
// Input example:
// { isbn, checkedAt, source:'authorized-api', copies:[
//   {barcode, homeLibrary, currentLibrary, shelfLocation, status:'在架', borrowable:true, reservationCount:0}
// ] }
const NON_CIRCULATING = /展覽用書|不外借|限館內閱覽|僅限館內|館內閱覽|參考資料區|參考書區/;
const ON_SHELF = /^在架(?:\s|$|[（(])/;

export function classifyCopy(copy) {
  const status = String(copy?.status ?? '').trim();
  const shelfLocation = String(copy?.shelfLocation ?? '').trim();
  const homeLibrary = String(copy?.homeLibrary ?? '').trim();
  const currentLibrary = String(copy?.currentLibrary ?? '').trim();
  const restriction = NON_CIRCULATING.test([status, shelfLocation, homeLibrary, currentLibrary].join(' '));
  const explicitEligibility = copy?.borrowable === true || copy?.borrowable === false;
  const canBorrow = !restriction && copy?.borrowable === true;
  const onShelf = ON_SHELF.test(status);
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
    availableToBorrow: canBorrow && onShelf,
    inLibraryReading: restriction && onShelf,
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
  const liveVerified = source === 'authorized-api' && validAge;
  const unverifiedCopyCount = copies.filter(c => c.potentiallyBorrowableButUnverified).length;
  let observedStatus = 'unknown';
  if (available.length > 0) observedStatus = 'available';
  else if (borrowable.length > 0) observedStatus = 'waiting';
  else if (reading.length > 0 && unverifiedCopyCount === 0) observedStatus = 'in_library_only';
  // 不可外借和一般在架副本同時存在，應以可借副本為準。
  // 有未確認可借資格的複本時，不得宣稱全市「僅館內閱讀」。
  return {
    isbn: String(record?.isbn ?? ''),
    checkedAt,
    source,
    liveVerified,
    status: validAge ? observedStatus : 'needs_refresh',
    observedStatus,
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
