import { useEffect, useMemo, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import type { CapturePageItem } from './mobileCapture.types';
import {
  deleteCapturePage,
  reorderCapturePages,
  updateCapturePageQuad,
  replaceCapturePageImage
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
import { CapturePhotoButton, type CapturePhotoButtonHandle } from './CapturePhotoButton';
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

function getStatusDetail(uploadedCount: number, hasSelectedPage: boolean) {
  if (hasSelectedPage) return '将上传原图与框选坐标';
  if (uploadedCount > 0) return `已采集 ${uploadedCount} 页，可删除、调整页序或补拍`;
  return '请拍摄病历文书页面，完成后回到电脑端审核';
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

function arrayToQuadByCorner(points: Array<{ x: number; y: number }> | null | undefined, width: number, height: number): QuadPointsByCorner {
  if (!Array.isArray(points) || points.length !== 4) {
    return createDefaultQuad(width, height);
  }
  const [tl, tr, br, bl] = points;
  if (![tl, tr, br, bl].every((point) => Number.isFinite(point?.x) && Number.isFinite(point?.y))) {
    return createDefaultQuad(width, height);
  }
  return { tl, tr, br, bl };
}

function toInitialPages(session: CaptureSession): CapturePageItem[] {
  return (session.pages ?? []).map((page, index) => {
    const width = page.image_width ?? PREVIEW_WIDTH;
    const height = page.image_height ?? PREVIEW_HEIGHT;
    return {
      localId: page.page_id,
      pageId: page.page_id,
      pageNo: index + 1,
      status: 'uploaded',
      width,
      height,
      quad: arrayToQuadByCorner(page.quad_points, width, height)
    };
  });
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
  const photoButtonRef = useRef<CapturePhotoButtonHandle>(null);
  const [editingPage, setEditingPage] = useState<CapturePageItem | null>(null);
  const [editMode, setEditMode] = useState<'new' | 'replace' | 'quad' | null>(null);
  const pagesRef = useRef<CapturePageItem[]>([]);
  const selectedPageRef = useRef<CapturePageItem | null>(null);

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

  useEffect(() => {
    pagesRef.current = pages;
    selectedPageRef.current = selectedPage;
  }, [pages, selectedPage]);

  useEffect(() => () => {
    const previewUrls = new Set<string>();
    pagesRef.current.forEach((page) => {
      if (page.previewUrl) previewUrls.add(page.previewUrl);
    });
    if (selectedPageRef.current?.previewUrl) {
      previewUrls.add(selectedPageRef.current.previewUrl);
    }
    previewUrls.forEach(revokePreviewUrl);
  }, []);

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

    if (editMode === 'replace' && editingPage) {
      const page: CapturePageItem = {
        localId: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        pageId: editingPage.pageId,
        pageNo: editingPage.pageNo,
        status: 'failed',
        previewUrl: createPreviewUrl(file),
        file,
        width: PREVIEW_WIDTH,
        height: PREVIEW_HEIGHT,
        quad: createDefaultQuad(PREVIEW_WIDTH, PREVIEW_HEIGHT)
      };
      setSelectedPage(page);
    } else {
      const page = buildLocalPage(file, pages.length);
      setSelectedPage(page);
    }
    setError(null);
  }

  function startNewPage() {
    if (isReadOnly) return;
    setEditingPage(null);
    setEditMode('new');
  }

  function startReplacePage(page: CapturePageItem) {
    if (isReadOnly) return;
    setEditingPage(page);
    setEditMode('replace');
    photoButtonRef.current?.trigger();
  }

  function startRequadPage(page: CapturePageItem) {
    if (isReadOnly || !page.pageId) return;
    setEditingPage(page);
    setSelectedPage(page);
    setEditMode('quad');
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

  async function handleConfirm() {
    if (!selectedPage) return;

    if (editMode === 'quad' && editingPage?.pageId) {
      if (!isValidQuad(selectedPage.quad)) {
        setError('框选区域无效，请重新调整');
        return;
      }
      setError(null);
      try {
        await updateCapturePageQuad(sessionId, editingPage.pageId, quadToArray(selectedPage.quad));
        setPages(current =>
          current.map(p => p.pageId === editingPage.pageId
            ? { ...p, quad: selectedPage.quad }
            : p
          )
        );
      } catch (err) {
        setError(getErrorMessage(err, '框选更新失败'));
        return;
      }
      resetEditState();
      return;
    }

    if (editMode === 'replace' && editingPage?.pageId && selectedPage.file) {
      if (!isValidQuad(selectedPage.quad)) {
        setError('框选区域无效，请重新调整');
        return;
      }
      setError(null);
      try {
        const result = await replaceCapturePageImage(sessionId, editingPage.pageId, {
          file: selectedPage.file,
          width: selectedPage.width,
          height: selectedPage.height,
          quad_points: quadToArray(selectedPage.quad)
        });
        const uploaded: CapturePageItem = {
          ...selectedPage,
          pageId: result.page_id,
          pageNo: editingPage.pageNo,
          status: 'uploaded'
        };
        setPages(current => {
          const next = current.map(p =>
            (p.pageId === editingPage.pageId || p.localId === editingPage.localId)
              ? uploaded
              : p
          );
          return renumberPages(next);
        });
      } catch (err) {
        setError(getErrorMessage(err, '替换失败，请重试'));
        return;
      }
      resetEditState();
      return;
    }

    // Default: new upload
    await uploadPage(selectedPage);
    setEditingPage(null);
    setEditMode(null);
  }

  async function retryUpload(page: CapturePageItem) {
    await uploadPage(page);
  }

  async function deletePage(page: CapturePageItem) {
    if (isReadOnly || !window.confirm(`确认删除第 ${page.pageNo} 页？`)) return;
    if (page.pageId) {
      try {
        await deleteCapturePage(sessionId, page.pageId);
      } catch {
        setError('删除失败，请重试');
        return;
      }
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

  function getConfirmLabel() {
    if (editMode === 'quad') return '确认框选';
    if (editMode === 'replace') return '确认替换';
    return '确认上传';
  }

  function resetEditState() {
    setSelectedPage(null);
    setEditingPage(null);
    setEditMode(null);
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
          <span className="mobile-capture__status-detail">
            {getStatusDetail(uploadedCount, Boolean(selectedPage))}
          </span>
        </div>

        {sessionStatus === 'locked' ? (
          <div className="mobile-capture__notice">采集完成，请在电脑端继续审核</div>
        ) : null}

        {error ? <div className="mobile-capture__error">{error}</div> : null}

        {isHelpOpen ? (
          <section className="mobile-capture__help" aria-label="采集帮助">
            <p>拍摄或选择图片后，请确认四个角点覆盖病历页面。</p>
            <p>请保持页面清晰、完整，避免反光和遮挡；采集完成后回到电脑端继续审核。</p>
          </section>
        ) : null}

        {selectedPage ? (
          <CaptureQuadScreen
            previewUrl={selectedPage.previewUrl}
            quad={selectedPage.quad}
            width={selectedPage.width}
            height={selectedPage.height}
            isUploading={selectedPage.status === 'uploading'}
            confirmLabel={getConfirmLabel()}
            cancelLabel={editMode === 'quad' ? '取消' : '重拍'}
            onChangeQuad={(quad) => setSelectedPage({ ...selectedPage, quad })}
            onResetQuad={() => setSelectedPage({ ...selectedPage, quad: createDefaultQuad(PREVIEW_WIDTH, PREVIEW_HEIGHT) })}
            onCancel={resetEditState}
            onConfirm={handleConfirm}
          />
        ) : (
          <>
            <section className="capture-card" aria-label="采集入口">
              <h2>请拍摄病历文书页面</h2>
              <p>确保病历页面完整、清晰、无反光，拍摄完成后上传。</p>
              <div className="capture-card__count">
                <span>已采集</span>
                <strong>{uploadedCount}</strong>
                <span>页</span>
              </div>
              <div className="capture-actions">
                <CapturePhotoButton
                  ref={photoButtonRef}
                  disabled={isReadOnly}
                  onFileSelected={handleFileSelected}
                  onClick={startNewPage}
                />
              </div>
            </section>

            <CapturePageList
              pages={pages}
              isReadOnly={isReadOnly}
              onDelete={deletePage}
              onRetry={retryUpload}
              onSupplement={startReplacePage}
              onRequad={startRequadPage}
              onReorder={reorderPages}
            />
          </>
        )}
      </section>

      {!selectedPage ? (
        <CaptureFooter
          disabled={isReadOnly}
          isFinishing={isFinishing}
          onCaptureNext={() => {
            startNewPage();
            photoButtonRef.current?.trigger();
          }}
          onFinish={finishCapture}
        />
      ) : null}
    </main>
  );
}
