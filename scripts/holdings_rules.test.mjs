import assert from 'node:assert/strict';
import { classifyCopy, summarizeHoldings } from './holdings_rules.mjs';

const now = new Date('2026-11-05T08:00:00Z');
const metadata = { source:'authorized-api', checkedAt:'2026-11-05T07:55:00Z' };
const borrowable = (status, reservationCount=0) => ({
  status, borrowable: true, reservationCount,
  homeLibrary:'安平區圖書館', currentLibrary:'安平區圖書館', shelfLocation:'兒童書區'
});
const exhibition = {
  status:'展覽用書(不外借)', borrowable:false, reservationCount:0,
  homeLibrary:'新總館', currentLibrary:'新總館', shelfLocation:'新總館B1兒童書區'
};
const readOnly = {
  status:'在架', borrowable:true, reservationCount:0, shelfLocation:'新總館4F參考資料區（限館內閱覽）'
};
const get = (copies, overrides={}) => summarizeHoldings({...metadata, isbn:'9789863203629',copies,...overrides},{now});

{
 const r=get([exhibition]);
 assert.equal(r.status,'in_library_only');
 assert.equal(r.availableBorrowableCopies,0);
 assert.equal(r.minReservationCount,null);
}
{
 const r=get([exhibition,borrowable('在架',2)]);
 assert.equal(r.status,'available');
 assert.equal(r.availableBorrowableCopies,1);
 assert.equal(r.inLibraryReadingCopies,1);
 assert.deepEqual(r.availableLibraries,['安平區圖書館']);
}
{
 const r=get([borrowable('借出 2026/11/29',3)]);
 assert.equal(r.status,'waiting');
 assert.equal(r.minReservationCount,3);
}
{
 const r=get([readOnly]);
 assert.equal(r.status,'in_library_only');
 assert.equal(r.availableBorrowableCopies,0);
}
{
 const r=get([{status:'在架',homeLibrary:'永康區圖書館',shelfLocation:'兒童書區'}]);
 assert.equal(r.status,'unknown');
 assert.equal(r.availableBorrowableCopies,0);
}
{
 const r=get([exhibition,{status:'在架',homeLibrary:'永康區圖書館',shelfLocation:'兒童書區'}]);
 assert.equal(r.status,'unknown');
 assert.equal(r.inLibraryReadingCopies,1);
}
{
 const r=get([borrowable('在架')],{checkedAt:'2026-11-05T06:00:00Z'});
 assert.equal(r.status,'needs_refresh');
 assert.equal(r.liveVerified,false);
}
{
 const r=get([borrowable('在架')],{source:'manual-import'});
 assert.equal(r.status,'available');
 assert.equal(r.liveVerified,false);
}
{
 const r=get([exhibition,borrowable('借出 2026/11/29',4)]);
 assert.equal(r.status,'waiting');
 assert.equal(r.minReservationCount,4);
}
{
 assert.equal(classifyCopy({status:'在架',borrowable:false}).availableToBorrow,false);
 assert.equal(classifyCopy({status:'尋書未獲',borrowable:true}).availableToBorrow,false);
 assert.equal(classifyCopy({status:'在架',borrowable:true,shelfLocation:'限館內閱覽'}).availableToBorrow,false);
 assert.equal(classifyCopy({status:'在架',borrowable:true,circulationPolicy:'展覽用書(不外借)'}).availableToBorrow,false);
 assert.equal(classifyCopy({status:'在架',borrowable:true,dataType:'中文參考書'}).availableToBorrow,false);
}
{
 const r=get([]);
 assert.equal(r.observedStatus,'unknown');
 assert.equal(r.availableBorrowableCopies,0);
}
{
 const c=classifyCopy({status:'展覽用書(可外借)',borrowable:true,homeLibrary:'白河年度新書區',currentLibrary:'白河年度新書區'});
 assert.equal(c.nonCirculating,false);
 assert.equal(c.canBorrow,true);
 assert.equal(c.availableToBorrow,true);
}
{
 const c=classifyCopy({status:'展覽用書(可外借)',borrowable:true,homeLibrary:'左鎮年度新書區(閉館整修)',currentLibrary:'左鎮年度新書區(閉館整修)'});
 assert.equal(c.canBorrow,true);
 assert.equal(c.availableToBorrow,false);
 assert.equal(c.accessUnavailable,true);
}
{
 const r=get([exhibition],{complete:false,source:'manual-html-snapshot'});
 assert.equal(r.observedStatus,'unknown'); // 單頁不足以證明全市只有展示本
 assert.equal(r.inLibraryReadingCopies,1);
 assert.equal(r.liveVerified,false);
}
{
 const r=get([borrowable('借出 2026/11/29',2)],{complete:false,source:'manual-html-snapshot'});
 assert.equal(r.observedStatus,'unknown'); // 單頁不足以證明全市都借出
}
{
 const r=get([borrowable('在架',0)],{complete:false,source:'authorized-api'});
 assert.equal(r.liveVerified,false); // API 不完整也不能標示即時完整
}
console.log('PASS: 16 verified test scenarios; no live catalog API was used.');
