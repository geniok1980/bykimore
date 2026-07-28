"use client";
import { useState, useCallback, useRef } from "react";

export const useModal = (initialState: boolean = false) => {
  const [isOpen, setIsOpen] = useState(initialState);
  const wasOpenedRef = useRef(false);

  const openModal = useCallback(() => {
    setIsOpen(true);
    wasOpenedRef.current = true;
  }, []);

  const closeModal = useCallback(() => {
    setIsOpen(false);
    wasOpenedRef.current = false;
  }, []);

  const toggleModal = useCallback(() => {
    setIsOpen((prev) => {
      wasOpenedRef.current = !prev;
      return !prev;
    });
  }, []);

  // Считываем состояние: если был открыт хотя бы раз, храним его до явного сброса
  const realIsOpen = isOpen || wasOpenedRef.current;

  return { isOpen: realIsOpen, openModal, closeModal, toggleModal };
};
