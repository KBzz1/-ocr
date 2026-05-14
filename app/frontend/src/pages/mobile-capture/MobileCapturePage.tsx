import { useEffect, useMemo, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import type { CapturePageItem } from './mobileCapture.types';
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
  quadToArray,
  type QuadPointsByCorner
} from '../../components/mobile-capture/QuadSelector';
import { CapturePhotoButton } from './CapturePhotoButton';
import { CapturePageList } from './CapturePageList';
import { CaptureQuadScreen } from './CaptureQuadScreen';
import { CaptureFooter } from './CaptureFooter';
import './mobile-capture.css';

const MAX_IMAGE_SIZE = 20 * 1024 * 1024;
const PREVIEW_WIDTH = 1000;
const PREVIEW_HEIGHT = 1400;

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
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const cameraInputRef = useRef<HTMLInputElement>(null);

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

    const page = buildLocalPage(file, pages.length);
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
            : [...current, uploaded];
        return renumberPages(next);
      });
      setSelectedPage(null);
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

  async function reorderPages(fromIndex: number, toIndex: number) {
    if (isReadOnly) return;
    const previous = pages;
    const next = [...pages];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
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

  function handleSupplement(page: CapturePageItem) {
    if (isReadOnly) return;
    // 补拍将在 Task 8 中实现替换逻辑，目前先触发新的拍照
    cameraInputRef.current?.click();
  }

  function handleRequad(page: CapturePageItem) {
    if (isReadOnly) return;
    // 重新框选将在后续任务中实现
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

        {selectedPage ? (
          <CaptureQuadScreen
            previewUrl={selectedPage?.previewUrl}
            quad={selectedPage?.quad ?? createDefaultQuad(PREVIEW_WIDTH, PREVIEW_HEIGHT)}
            width={selectedPage?.width ?? PREVIEW_WIDTH}
            height={selectedPage?.height ?? PREVIEW_HEIGHT}
            isUploading={selectedPage?.status === 'uploading'}
            confirmLabel="确认上传"
            onChangeQuad={(quad) => selectedPage && setSelectedPage({ ...selectedPage, quad })}
            onResetQuad={() => selectedPage && setSelectedPage({ ...selectedPage, quad: createDefaultQuad(PREVIEW_WIDTH, PREVIEW_HEIGHT) })}
            onCancel={() => setSelectedPage(null)}
            onConfirm={() => selectedPage && uploadPage(selectedPage)}
          />
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
                <CapturePhotoButton
                  disabled={isReadOnly}
                  onFileSelected={handleFileSelected}
                />
              </div>
            </section>

            <CapturePageList
              pages={pages}
              isReadOnly={isReadOnly}
              onDelete={deletePage}
              onRetry={retryUpload}
              onSupplement={handleSupplement}
              onRequad={handleRequad}
              onReorder={reorderPages}
            />
          </>
        )}
      </section>

      <CaptureFooter
        disabled={isReadOnly}
        isFinishing={isFinishing}
        canFinish={true}
        onCaptureNext={() => cameraInputRef.current?.click()}
        onFinish={finishCapture}
      />
    </main>
  );
}
