import { useEffect, useMemo, useState } from 'react';

import { getApiErrorMessage } from '../../api/client';
import {
  deleteTaskImage,
  finishTaskUpload,
  getTaskUploadStatus,
  uploadTaskImage,
  type UploadedImage
} from '../../api/mobileUpload';
import { CapturePhotoButton } from './CapturePhotoButton';
import { CapturePageList } from './CapturePageList';
import { CaptureFooter } from './CaptureFooter';
import type { CapturePageItem } from './mobileCapture.types';
import './mobile-capture.css';

const MAX_IMAGE_SIZE = 20 * 1024 * 1024;

type MobileCapturePageProps = {
  taskId?: string;
  token?: string;
  initialImages?: UploadedImage[];
};

function getTaskIdFromLocation() {
  const segments = window.location.pathname.split('/').filter(Boolean);
  return decodeURIComponent(segments[segments.length - 1] ?? '');
}

function getTokenFromLocation() {
  return new URLSearchParams(window.location.search).get('token') ?? '';
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

function toPageItem(image: UploadedImage): CapturePageItem {
  return {
    localId: image.page_id,
    pageId: image.page_id,
    taskId: image.task_id,
    pageNo: image.page_no,
    status: 'uploaded',
    previewUrl: image.preview_url
  };
}

function movePage(pages: CapturePageItem[], fromIndex: number, toIndex: number) {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return pages;
  if (fromIndex >= pages.length || toIndex >= pages.length) return pages;
  const nextPages = [...pages];
  const [movedPage] = nextPages.splice(fromIndex, 1);
  nextPages.splice(toIndex, 0, movedPage);
  return nextPages.map((page, index) => ({ ...page, pageNo: index + 1 }));
}

export function MobileCapturePage({
  taskId: taskIdProp,
  token: tokenProp,
  initialImages = []
}: MobileCapturePageProps) {
  const taskId = useMemo(() => taskIdProp ?? getTaskIdFromLocation(), [taskIdProp]);
  const token = useMemo(() => tokenProp ?? getTokenFromLocation(), [tokenProp]);
  const [pages, setPages] = useState<CapturePageItem[]>(() => initialImages.map(toPageItem));
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [isFinished, setIsFinished] = useState(false);
  const [isClearConfirmOpen, setIsClearConfirmOpen] = useState(false);
  const [documentTypeLabel, setDocumentTypeLabel] = useState('');

  useEffect(() => {
    if (!taskId || !token || initialImages.length > 0) return;

    let isMounted = true;
    getTaskUploadStatus(taskId, token)
      .then((status) => {
        if (!isMounted) return;
        setPages(status.images.map(toPageItem));
        setIsFinished(status.status !== 'uploading');
        setDocumentTypeLabel(status.document_type_label ?? status.document_type ?? '');
      })
      .catch((statusError) => {
        if (!isMounted) return;
        setError(getApiErrorMessage(statusError, '上传状态加载失败，请重新扫描二维码'));
      });

    return () => {
      isMounted = false;
    };
  }, [initialImages.length, taskId, token]);

  async function handleFilesSelected(files: FileList | null) {
    if (!files || !taskId || !token || isFinished || isFinishing) return;
    const selectedFiles = Array.from(files);
    if (selectedFiles.length === 0) return;

    setError(null);
    const acceptedPages: CapturePageItem[] = [];

    for (const file of selectedFiles) {
      if (!isSupportedImage(file)) {
        setError('不支持的文件类型');
        continue;
      }
      if (file.size > MAX_IMAGE_SIZE) {
        setError('图片过大（最大 20MB）');
        continue;
      }

      const localId = `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const localPage: CapturePageItem = {
        localId,
        taskId,
        pageNo: pages.length + acceptedPages.length + 1,
        status: 'pending',
        previewUrl: createPreviewUrl(file),
        fileName: file.name,
        file
      };
      acceptedPages.push(localPage);
    }

    if (acceptedPages.length > 0) {
      setPages((current) => [...current, ...acceptedPages].map((page, index) => ({ ...page, pageNo: index + 1 })));
    }
  }

  async function uploadPendingPages() {
    const pagesToUpload = pages.filter((page) => (page.status === 'pending' || page.status === 'failed') && page.file);
    if (pagesToUpload.length === 0) return true;

    setIsUploading(true);
    let hasFailure = false;
    for (const pageToUpload of pagesToUpload) {
      setPages((current) =>
        current.map((page) =>
          page.localId === pageToUpload.localId
            ? { ...page, status: 'uploading', errorMessage: undefined }
            : page
        )
      );
      try {
        const uploaded = await uploadTaskImage(taskId, token, pageToUpload.file as File);
        setPages((current) =>
          current.map((page) =>
            page.localId === pageToUpload.localId
              ? {
                  ...toPageItem(uploaded),
                  localId: page.localId,
                  previewUrl: page.previewUrl,
                  fileName: page.fileName,
                  file: undefined
                }
              : page
          )
        );
      } catch (uploadError) {
        hasFailure = true;
        setPages((current) =>
          current.map((page) =>
            page.localId === pageToUpload.localId
              ? { ...page, status: 'failed', errorMessage: getApiErrorMessage(uploadError, '上传失败，请重试') }
              : page
          )
        );
      }
    }
    setIsUploading(false);
    return !hasFailure;
  }

  async function handleDeletePage(pageToDelete: CapturePageItem) {
    if (isFinishing || isUploading) return;
    setError(null);
    if (pageToDelete.status === 'uploaded' && pageToDelete.pageId) {
      try {
        const status = await deleteTaskImage(taskId, token, pageToDelete.pageId);
        setPages((current) => {
          const localPending = current.filter((page) => page.status !== 'uploaded' && page.localId !== pageToDelete.localId);
          return [...status.images.map(toPageItem), ...localPending].map((page, index) => ({ ...page, pageNo: index + 1 }));
        });
      } catch (deleteError) {
        setError(getApiErrorMessage(deleteError, '删除图片失败，请重试'));
      }
      return;
    }

    setPages((current) =>
      current
        .filter((page) => page.localId !== pageToDelete.localId)
        .map((page, index) => ({ ...page, pageNo: index + 1 }))
    );
  }

  function handleRequestClearAll() {
    if (isFinishing || isUploading || pages.length === 0) return;
    setIsClearConfirmOpen(true);
  }

  async function handleConfirmClearAll() {
    if (isFinishing || isUploading || pages.length === 0) return;
    setError(null);
    const uploadedPages = pages.filter((page) => page.status === 'uploaded' && page.pageId);
    try {
      for (const page of uploadedPages) {
        await deleteTaskImage(taskId, token, page.pageId as string);
      }
      setPages([]);
      setIsClearConfirmOpen(false);
    } catch (deleteError) {
      setError(getApiErrorMessage(deleteError, '清除图片失败，请重试'));
      // 部分删除可能已经成功,重新同步服务端状态避免本地与服务端分叉
      try {
        const status = await getTaskUploadStatus(taskId, token);
        setPages((current) => {
          const localPending = current.filter((page) => page.status !== 'uploaded');
          const syncedImages = status.images.map(toPageItem);
          return [...syncedImages, ...localPending].map((page, index) => ({ ...page, pageNo: index + 1 }));
        });
      } catch {
        // 同步失败仍保留错误提示,用户可手动刷新
      }
    }
  }

  function handleReorderPages(fromIndex: number, toIndex: number) {
    if (isFinishing || isUploading || isFinished) return;
    setPages((current) => movePage(current, fromIndex, toIndex));
  }

  async function handleFinish() {
    if (!taskId || !token || pages.length === 0) return;
    setIsFinishing(true);
    setError(null);
    try {
      const uploadedOk = await uploadPendingPages();
      if (!uploadedOk) {
        setError('部分图片上传失败，请删除或重新上传后再完成');
        return;
      }
      await finishTaskUpload(taskId, token);
      setIsFinished(true);
    } catch (finishError) {
      setError(getApiErrorMessage(finishError, '完成上传失败，请重试'));
    } finally {
      setIsFinishing(false);
    }
  }

  const selectedCount = pages.length;
  const canUpload = Boolean(taskId && token && !isFinished && !isUploading && !isFinishing);

  return (
    <main className="mobile-capture" aria-label="手机上传页">
      <header className="mobile-capture__topbar">
        <button className="mobile-capture__icon-button" type="button" aria-label="返回" onClick={() => window.history.back()}>
          ‹
        </button>
        <h1>手机上传</h1>
        <span className="mobile-capture__icon-button" aria-hidden="true" />
      </header>

      <section className="mobile-capture__body">
        <div className="mobile-capture__status-row">
          <span className="mobile-capture__status-pill is-active">
            {isFinished ? '上传已完成' : '任务上传中'}
          </span>
          <span className="mobile-capture__status-detail">
            已选择 {selectedCount} 张图片
          </span>
        </div>

        {isFinished ? (
          <div className="mobile-capture__notice">上传已完成，请回到电脑端查看处理结果</div>
        ) : null}

        {!taskId || !token ? (
          <div className="mobile-capture__error">无效的上传链接，请重新扫描二维码</div>
        ) : null}
        {error ? <div className="mobile-capture__error">{error}</div> : null}

        {documentTypeLabel ? (
          <section className="capture-card capture-card--template">
            <span>记录类型</span>
            <strong>{documentTypeLabel}</strong>
          </section>
        ) : null}

        <section className="capture-card" aria-label="上传入口">
          <h2>请上传病历图片</h2>
          <div className="capture-card__count">
            <span>已选择</span>
            <strong>{selectedCount}</strong>
            <span>张</span>
          </div>
          <div className="capture-actions">
            <CapturePhotoButton disabled={!canUpload} onFilesSelected={handleFilesSelected} />
          </div>
        </section>

        <CapturePageList
          pages={pages}
          canDelete={!isFinished && !isFinishing && !isUploading}
          canReorder={!isFinished && !isFinishing && !isUploading && pages.length > 0}
          onDelete={handleDeletePage}
          onReorder={handleReorderPages}
        />
      </section>

      <CaptureFooter
        canFinish={!isFinished && selectedCount > 0}
        isFinishing={isFinishing || isUploading}
        canReset={!isFinished && selectedCount > 0}
        onFinish={handleFinish}
        onReset={handleRequestClearAll}
      />
      {isClearConfirmOpen ? (
        <div className="mobile-confirm-backdrop" role="presentation" onMouseDown={() => setIsClearConfirmOpen(false)}>
          <section
            className="mobile-confirm"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="clear-images-title"
            aria-describedby="clear-images-description"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="clear-images-title">清除所有图片？</h2>
            <p id="clear-images-description">
              将删除当前任务中已上传的图片，并清空本机待上传图片。此操作不可恢复。
            </p>
            <footer className="mobile-confirm__actions">
              <button className="mobile-button ghost" type="button" onClick={() => setIsClearConfirmOpen(false)}>
                取消
              </button>
              <button className="mobile-button" type="button" onClick={() => void handleConfirmClearAll()}>
                确认清除
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </main>
  );
}
