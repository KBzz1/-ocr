import { useEffect, useMemo, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import {
  deleteCapturePage,
  reorderCapturePages
} from './mobileCaptureApi';
import {
  finishCaptureSession,
  getCaptureSession,
  uploadCapturePage,
  type CaptureSession,
  type CaptureSessionStatus
} from '../../api/captureSessions';
import {
  createDefaultQuad,
  isValidQuad,
  QuadSelector,
  quadToArray,
  type QuadPointsByCorner
} from '../../components/mobile-capture/QuadSelector';
import './mobile-capture.css';

const MAX_IMAGE_SIZE = 20 * 1024 * 1024;
const PREVIEW_WIDTH = 1000;
const PREVIEW_HEIGHT = 1400;

type PageStatus = 'uploaded' | 'uploading' | 'failed';

interface CapturePageItem {
  localId: string;
  pageId?: string;
  pageNo: number;
  status: PageStatus;
  previewUrl?: string;
  file?: File;
  width: number;
  height: number;
  quad: QuadPointsByCorner;
}

function getSessionIdFromLocation() {
  const querySession = new URLSearchParams(window.location.search).get('session');
  if (querySession) return querySession;

  const segments = window.location.pathname.split('/').filter(Boolean);
  return decodeURIComponent(segments[segments.length - 1] ?? '');
}

function getStatusCopy(status: CaptureSessionStatus | 'invalid' | 'loading') {
  if (status === 'active') return '采集会话进行中';
  if (status === 'expired') return '采集会话已过期';
  if (status === 'locked') return '采集已完成，请在电脑端查看';
  if (status === 'loading') return '正在加载采集会话';
  return '无效的采集链接，请重新扫描二维码';
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function isSupportedImage(file: File) {
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  return (
    type === 'image/jpeg' ||
    type === 'image/png' ||
    type === 'image/bmp' ||
    /\.(jpe?g|png|bmp)$/.test(name)
  );
}

function createPreviewUrl(file: File) {
  if (typeof URL !== 'undefined' && 'createObjectURL' in URL) {
    return URL.createObjectURL(file);
  }

  return '';
}

function revokePreviewUrl(url?: string) {
  if (url && typeof URL !== 'undefined' && 'revokeObjectURL' in URL) {
    URL.revokeObjectURL(url);
  }
}

function toInitialPages(session: CaptureSession): CapturePageItem[] {
  return (session.pages ?? []).map((page, index) => ({
    localId: page.page_id,
    pageId: page.page_id,
    pageNo: index + 1,
    status: 'uploaded',
    width: PREVIEW_WIDTH,
    height: PREVIEW_HEIGHT,
    quad: createDefaultQuad(PREVIEW_WIDTH, PREVIEW_HEIGHT)
  }));
}

function renumberPages(pages: CapturePageItem[]) {
  return pages.map((page, index) => ({ ...page, pageNo: index + 1 }));
}

function buildLocalPage(file: File, insertAt: number): CapturePageItem {
  return {
    localId: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    pageNo: insertAt + 1,
    status: 'failed',
    previewUrl: createPreviewUrl(file),
    file,
    width: PREVIEW_WIDTH,
    height: PREVIEW_HEIGHT,
    quad: createDefaultQuad(PREVIEW_WIDTH, PREVIEW_HEIGHT)
  };
}

export function MobileCapturePage() {
  const sessionId = useMemo(getSessionIdFromLocation, []);
  const [sessionStatus, setSessionStatus] = useState<CaptureSessionStatus | 'invalid' | 'loading'>(
    sessionId ? 'loading' : 'invalid'
  );
  const [pages, setPages] = useState<CapturePageItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<CapturePageItem | null>(null);
  const [isFinishing, setIsFinishing] = useState(false);
  const [insertIndex, setInsertIndex] = useState<number | null>(null);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const libraryInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!sessionId) return;

    let isActive = true;
    getCaptureSession(sessionId)
      .then((session) => {
        if (!isActive) return;
        setSessionStatus(session.status);
        setPages(toInitialPages(session));
        setError(null);
      })
      .catch(() => {
        if (!isActive) return;
        setSessionStatus('invalid');
        setPages([]);
      });

    return () => {
      isActive = false;
    };
  }, [sessionId]);

  useEffect(
    () => () => {
      pages.forEach((page) => revokePreviewUrl(page.previewUrl));
      if (selectedPage && !pages.some((page) => page.localId === selectedPage.localId)) {
        revokePreviewUrl(selectedPage.previewUrl);
      }
    },
    [pages, selectedPage]
  );

  const isReadOnly = sessionStatus !== 'active';
  const uploadedCount = pages.filter((page) => page.status === 'uploaded').length;
  const statusCopy = getStatusCopy(sessionStatus);
  const title = selectedPage ? '调整识别范围' : uploadedCount > 0 ? '已采集页面' : '病历文书采集';

  function pickFile(source: 'camera' | 'library') {
    if (isReadOnly) return;
    setError(null);
    if (source === 'camera') {
      cameraInputRef.current?.click();
      return;
    }
    libraryInputRef.current?.click();
  }

  function handleFileSelected(file: File | undefined) {
    if (!file) return;
    if (!isSupportedImage(file)) {
      setError('不支持的文件类型');
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      setError('图片过大（最大 20MB）');
      return;
    }

    const targetIndex = insertIndex ?? pages.length;
    const page = buildLocalPage(file, targetIndex);
    setSelectedPage(page);
    setError(null);
  }

  async function uploadPage(page: CapturePageItem) {
    if (!page.file || page.status === 'uploading') return;
    if (!isValidQuad(page.quad)) {
      setError('框选区域无效，请重新调整');
      return;
    }

    setError(null);
    const uploadingPage = { ...page, status: 'uploading' as const };
    if (selectedPage?.localId === page.localId) {
      setSelectedPage(uploadingPage);
    }
    setPages((current) =>
      current.some((item) => item.localId === page.localId)
        ? current.map((item) => (item.localId === page.localId ? uploadingPage : item))
        : current
    );

    try {
      const result = await uploadCapturePage(sessionId, {
        file: page.file,
        width: page.width,
        height: page.height,
        quad_points: quadToArray(page.quad)
      });
      const uploaded: CapturePageItem = {
        ...uploadingPage,
        pageId: result.page_id,
        status: 'uploaded'
      };
      setPages((current) => {
        const existingIndex = current.findIndex((item) => item.localId === uploaded.localId);
        const next =
          existingIndex >= 0
            ? current.map((item) => (item.localId === uploaded.localId ? uploaded : item))
            : [
                ...current.slice(0, insertIndex ?? current.length),
                uploaded,
                ...current.slice(insertIndex ?? current.length)
              ];
        return renumberPages(next);
      });
      setSelectedPage(null);
      setInsertIndex(null);
    } catch (uploadError) {
      const failed = { ...uploadingPage, status: 'failed' as const };
      setPages((current) => {
        const existingIndex = current.findIndex((item) => item.localId === failed.localId);
        const next =
          existingIndex >= 0
            ? current.map((item) => (item.localId === failed.localId ? failed : item))
            : [...current, failed];
        return renumberPages(next);
      });
      setSelectedPage(null);
      setError(getErrorMessage(uploadError, '上传失败，请重试'));
    }
  }

  async function retryUpload(page: CapturePageItem) {
    await uploadPage(page);
  }

  async function deletePage(page: CapturePageItem) {
    if (isReadOnly || !window.confirm(`确认删除第 ${page.pageNo} 页？`)) return;
    if (page.pageId) {
      await deleteCapturePage(sessionId, page.pageId).catch(() => {
        setError('删除失败，请重试');
        throw new Error('delete failed');
      });
    }

    setPages((current) => renumberPages(current.filter((item) => item.localId !== page.localId)));
  }

  async function movePage(index: number, direction: -1 | 1) {
    if (isReadOnly) return;
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= pages.length) return;

    const previous = pages;
    const next = [...pages];
    const [moved] = next.splice(index, 1);
    next.splice(targetIndex, 0, moved);
    const renumbered = renumberPages(next);
    setPages(renumbered);

    try {
      await reorderCapturePages(
        sessionId,
        renumbered.map((page) => page.pageId).filter((pageId): pageId is string => Boolean(pageId))
      );
    } catch {
      setPages(previous);
      setError('排序失败，请重试');
    }
  }

  function supplementPage(index: number | null = null) {
    if (isReadOnly) return;
    setInsertIndex(index);
    libraryInputRef.current?.click();
  }

  async function finishCapture() {
    if (isReadOnly || isFinishing) return;
    if (uploadedCount === 0) {
      setError('请至少采集一页病历');
      return;
    }

    setIsFinishing(true);
    setError(null);
    try {
      await finishCaptureSession(sessionId);
      setSessionStatus('locked');
      setError(null);
    } catch (finishError) {
      setError(getErrorMessage(finishError, '完成采集失败，请重试'));
    } finally {
      setIsFinishing(false);
    }
  }

  return (
    <main className="mobile-capture" aria-label="手机采集页">
      <header className="mobile-capture__topbar">
        <button className="mobile-capture__icon-button" type="button" aria-label="返回" onClick={() => window.history.back()}>
          ‹
        </button>
        <h1>{title}</h1>
        <button
          className="mobile-capture__icon-button"
          type="button"
          aria-label="帮助"
          aria-expanded={isHelpOpen}
          onClick={() => setIsHelpOpen((value) => !value)}
        >
          ?
        </button>
      </header>

      <section className="mobile-capture__body">
        <div className="mobile-capture__status-row">
          <span className={`mobile-capture__status-pill is-${sessionStatus}`}>{statusCopy}</span>
          <span>已采集 {uploadedCount} 页</span>
        </div>

        {sessionStatus === 'locked' ? (
          <div className="mobile-capture__notice">采集完成，请在电脑端继续审核</div>
        ) : null}

        {error ? <div className="mobile-capture__error">{error}</div> : null}

        {isHelpOpen ? (
          <section className="mobile-capture__help" aria-label="采集帮助">
            <p>拍照或选择图片后，请确认四个角点覆盖病历页面。</p>
            <p>请保持页面清晰、完整，避免反光和遮挡；采集完成后回到电脑端继续审核。</p>
          </section>
        ) : null}

        <input
          ref={cameraInputRef}
          className="visually-hidden-input"
          aria-label="拍照"
          type="file"
          accept="image/jpeg,image/png,image/bmp"
          capture="environment"
          disabled={isReadOnly}
          onChange={(event) => handleFileSelected(event.currentTarget.files?.[0])}
        />
        <input
          ref={libraryInputRef}
          className="visually-hidden-input"
          aria-label="选择已有图片"
          type="file"
          accept="image/jpeg,image/png,image/bmp"
          disabled={isReadOnly}
          onChange={(event) => handleFileSelected(event.currentTarget.files?.[0])}
        />

        {selectedPage ? (
          <section className="preview-panel" aria-label="上传预览">
            <p className="mobile-capture__hint">
              请框选病历正文区域，排除屏幕边缘、灰色背景和工具栏
            </p>
            <div className="preview-panel__image-wrap">
              <img src={selectedPage.previewUrl} alt="待上传病历页面预览" />
              <QuadSelector
                width={selectedPage.width}
                height={selectedPage.height}
                points={selectedPage.quad}
                onChange={(quad) => setSelectedPage({ ...selectedPage, quad })}
              />
            </div>
            <div className="capture-actions">
              <button className="mobile-button ghost" type="button" onClick={() => setSelectedPage(null)}>
                重拍
              </button>
              <button
                className="mobile-button secondary"
                type="button"
                onClick={() => setSelectedPage({ ...selectedPage, quad: createDefaultQuad(PREVIEW_WIDTH, PREVIEW_HEIGHT) })}
              >
                重新框选
              </button>
              <button
                className="mobile-button"
                type="button"
                disabled={selectedPage.status === 'uploading'}
                onClick={() => uploadPage(selectedPage)}
              >
                {selectedPage.status === 'uploading' ? '上传中' : '确认上传'}
              </button>
            </div>
          </section>
        ) : (
          <>
            <section className="capture-card" aria-label="采集入口">
              <h2>请拍摄病历文书页面</h2>
              <p>确保证件完整、清晰、无反光，拍摄完成后上传。</p>
              <div className="capture-card__count">
                <span>已采集</span>
                <strong>{uploadedCount}</strong>
                <span>页</span>
              </div>
              <div className="capture-actions">
                <button
                  className="mobile-button"
                  type="button"
                  disabled={isReadOnly}
                  onClick={() => pickFile('camera')}
                >
                  拍照
                </button>
                <button
                  className="mobile-button secondary"
                  type="button"
                  disabled={isReadOnly}
                  onClick={() => pickFile('library')}
                >
                  选择已有图片
                </button>
              </div>
            </section>

            <PageList
              pages={pages}
              isReadOnly={isReadOnly}
              onDelete={deletePage}
              onMove={movePage}
              onRetry={retryUpload}
              onSupplement={supplementPage}
            />

            <section className="supplement-card">
              <h2>补拍页面</h2>
              <p>若页面模糊、缺失或拍摄不完整，可补拍后替换该页。</p>
              <button
                className="mobile-button secondary"
                type="button"
                disabled={isReadOnly}
                onClick={() => supplementPage(pages.length)}
              >
                补拍页面
              </button>
            </section>
          </>
        )}
      </section>

      <footer className="mobile-capture__footer">
        <div className="mobile-capture__footer-inner">
          <button
            className="mobile-button secondary"
            type="button"
            disabled={isReadOnly}
            onClick={() => pickFile('camera')}
          >
            继续拍下一页
          </button>
          <button
            className="mobile-button"
            type="button"
            disabled={isReadOnly || isFinishing}
            onClick={finishCapture}
          >
            {isFinishing ? '提交中' : '完成采集'}
          </button>
        </div>
      </footer>
    </main>
  );
}

interface PageListProps {
  pages: CapturePageItem[];
  isReadOnly: boolean;
  onDelete: (page: CapturePageItem) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  onRetry: (page: CapturePageItem) => void;
  onSupplement: (index: number) => void;
}

function PageList({ pages, isReadOnly, onDelete, onMove, onRetry, onSupplement }: PageListProps) {
  return (
    <section className="page-list" aria-label="已采集页面列表">
      <div className="page-list__header">
        <div>
          <h2>已采集页面列表</h2>
          <p>上传后可在这里查看、删除或调整顺序</p>
        </div>
      </div>

      {pages.length === 0 ? (
        <div className="page-list__empty">
          <div>
            <strong>暂未上传页面</strong>
            <p>上传后可在这里查看、删除或调整顺序</p>
          </div>
        </div>
      ) : (
        <ol className="page-list__items">
          {pages.map((page, index) => (
            <li
              className="page-item"
              key={page.localId}
              aria-label={`第 ${index + 1} 页 ${page.status === 'failed' ? '上传失败' : '已上传'}`}
            >
              <div className="page-item__thumb">
                {page.previewUrl ? <img src={page.previewUrl} alt={`第 ${index + 1} 页缩略图`} /> : '缩略图'}
              </div>
              <div>
                <h3>第 {index + 1} 页</h3>
                <span className={`page-item__status is-${page.status}`}>
                  {page.status === 'failed'
                    ? '上传失败，请重试'
                    : page.status === 'uploading'
                      ? '上传中'
                      : '已上传'}
                </span>
                {page.pageId ? <span hidden>{page.pageId}</span> : null}
                {!isReadOnly ? (
                  <div className="page-item__actions">
                    {page.status === 'failed' ? (
                      <button type="button" onClick={() => onRetry(page)} aria-label={`重试第 ${index + 1} 页`}>
                        重试
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => onDelete(page)}
                      aria-label={`删除第 ${index + 1} 页`}
                    >
                      删除
                    </button>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() => onMove(index, -1)}
                      aria-label={`上移第 ${index + 1} 页`}
                    >
                      上移
                    </button>
                    <button
                      type="button"
                      disabled={index === pages.length - 1}
                      onClick={() => onMove(index, 1)}
                      aria-label={`下移第 ${index + 1} 页`}
                    >
                      下移
                    </button>
                    <button type="button" onClick={() => onSupplement(index + 1)}>
                      补拍
                    </button>
                  </div>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
