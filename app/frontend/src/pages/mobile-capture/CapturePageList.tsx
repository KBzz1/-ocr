import type { CapturePageItem as PageItem } from './mobileCapture.types';
import { CapturePageItem } from './CapturePageItem';

interface CapturePageListProps {
  pages: PageItem[];
}

export function CapturePageList({ pages }: CapturePageListProps) {
  return (
    <section className="page-list" aria-label="已上传图片列表">
      <div className="page-list__header">
        <div>
          <h2>图片列表</h2>
          <p>页序按上传成功顺序确定</p>
        </div>
      </div>
      {pages.length === 0 ? (
        <div className="page-list__empty">
          <div>
            <strong>暂未上传图片</strong>
            <p>上传后可在这里查看页序和文件名</p>
          </div>
        </div>
      ) : (
        <ol className="page-list__items">
          {pages.map((page, index) => (
            <CapturePageItem key={page.localId} page={page} index={index} />
          ))}
        </ol>
      )}
    </section>
  );
}
