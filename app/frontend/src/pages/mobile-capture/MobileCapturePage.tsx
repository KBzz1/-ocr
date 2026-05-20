import { useEffect, useMemo, useState } from 'react';

import { ApiError } from '../../api/client';
import { finishTaskUpload, getTaskUploadStatus, uploadTaskImage, type UploadedImage } from '../../api/mobileUpload';
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

  useEffect(() => {
    if (!taskId || !token || initialImages.length > 0) return;

    let isMounted = true;
    getTaskUploadStatus(taskId, token)
      .then((status) => {
        if (!isMounted) return;
        setPages(status.images.map(toPageItem));
        setIsFinished(status.status !== 'uploading');
      })
      .catch((statusError) => {
        if (!isMounted) return;
        setError(getErrorMessage(statusError, '上传状态加载失败，请重新扫描二维码'));
      });

    return () => {
      isMounted = false;
    };
  }, [initialImages.length, taskId, token]);

  async function handleFilesSelected(files: FileList | null) {
    if (!files || !taskId || !token || isFinished) return;
    const selectedFiles = Array.from(files);
    if (selectedFiles.length === 0) return;

    setIsUploading(true);
    setError(null);

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
        pageNo: pages.length + 1,
        status: 'uploading',
        previewUrl: createPreviewUrl(file),
        fileName: file.name
      };
      setPages((current) => [...current, localPage]);

      try {
        const uploaded = await uploadTaskImage(taskId, token, file);
        setPages((current) =>
          current.map((page) =>
            page.localId === localId
              ? { ...toPageItem(uploaded), localId, previewUrl: localPage.previewUrl, fileName: file.name }
              : page
          )
        );
      } catch (uploadError) {
        setPages((current) =>
          current.map((page) =>
            page.localId === localId
              ? { ...page, status: 'failed', errorMessage: getErrorMessage(uploadError, '上传失败，请重试') }
              : page
          )
        );
      }
    }

    setIsUploading(false);
  }

  async function handleFinish() {
    if (!taskId || !token || pages.filter((page) => page.status === 'uploaded').length === 0) return;
    setIsFinishing(true);
    setError(null);
    try {
      await finishTaskUpload(taskId, token);
      setIsFinished(true);
    } catch (finishError) {
      setError(getErrorMessage(finishError, '完成上传失败，请重试'));
    } finally {
      setIsFinishing(false);
    }
  }

  const uploadedCount = pages.filter((page) => page.status === 'uploaded').length;
  const canUpload = Boolean(taskId && token && !isFinished && !isUploading);

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
            已上传 {uploadedCount} 张图片
          </span>
        </div>

        {isFinished ? (
          <div className="mobile-capture__notice">上传已完成，请回到电脑端查看处理结果</div>
        ) : null}

        {!taskId || !token ? (
          <div className="mobile-capture__error">无效的上传链接，请重新扫描二维码</div>
        ) : null}
        {error ? <div className="mobile-capture__error">{error}</div> : null}

        <section className="capture-card" aria-label="上传入口">
          <h2>请上传病历文书图片</h2>
          <p>页序按上传成功顺序确定，请保持图片清晰完整。</p>
          <div className="capture-card__count">
            <span>已上传</span>
            <strong>{uploadedCount}</strong>
            <span>张</span>
          </div>
          <div className="capture-actions">
            <CapturePhotoButton disabled={!canUpload} onFilesSelected={handleFilesSelected} />
          </div>
        </section>

        <CapturePageList pages={pages} />
      </section>

      <CaptureFooter
        canFinish={!isFinished && uploadedCount > 0}
        isFinishing={isFinishing}
        onFinish={handleFinish}
      />
    </main>
  );
}
