"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface ChartErrorBoundaryProps {
  children: ReactNode;
  resetKey: string;
}

interface ChartErrorBoundaryState {
  failed: boolean;
}

export class ChartErrorBoundary extends Component<ChartErrorBoundaryProps, ChartErrorBoundaryState> {
  state: ChartErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ChartErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Candlestick chart failed safely", error, info.componentStack);
  }

  componentDidUpdate(previousProps: ChartErrorBoundaryProps) {
    if (this.state.failed && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="chart-safe-error" role="alert">
          <strong>K 线图暂时无法更新</strong>
          <span>其他行情与风险功能仍可继续使用。</span>
          <button type="button" onClick={() => this.setState({ failed: false })}>重新加载图表</button>
        </div>
      );
    }
    return this.props.children;
  }
}
