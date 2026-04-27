CREATE OR REPLACE PACKAGE PKG_AUTO_LOAN_APPROVAL AS

    -- 오토론 신청 접수
    PROCEDURE PROC_LOAN_APPLICATION_RECEIVE (
        p_customer_id      IN  TBL_CUSTOMER_MASTER.CUSTOMER_ID%TYPE,
        p_vehicle_price    IN  NUMBER,
        p_loan_amount      IN  NUMBER,
        p_loan_period      IN  NUMBER,
        p_application_id   OUT TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_result_code      OUT VARCHAR2
    );

    -- 신용평가
    PROCEDURE PROC_CREDIT_EVALUATION (
        p_application_id   IN  TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_result_code      OUT VARCHAR2
    );

    -- 대출 한도 산정
    FUNCTION FUNC_LIMIT_CALCULATION (
        p_customer_id      IN  TBL_CUSTOMER_MASTER.CUSTOMER_ID%TYPE,
        p_credit_score     IN  NUMBER
    ) RETURN NUMBER;

    -- 최종 승인 처리
    PROCEDURE PROC_FINAL_APPROVAL (
        p_application_id   IN  TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_result_code      OUT VARCHAR2
    );

    -- 신청자 알림
    PROCEDURE PROC_NOTIFY_APPLICANT (
        p_application_id   IN  TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_notify_type      IN  VARCHAR2
    );

END PKG_AUTO_LOAN_APPROVAL;
/

CREATE OR REPLACE PACKAGE BODY PKG_AUTO_LOAN_APPROVAL AS

    PROCEDURE PROC_LOAN_APPLICATION_RECEIVE (
        p_customer_id      IN  TBL_CUSTOMER_MASTER.CUSTOMER_ID%TYPE,
        p_vehicle_price    IN  NUMBER,
        p_loan_amount      IN  NUMBER,
        p_loan_period      IN  NUMBER,
        p_application_id   OUT TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_result_code      OUT VARCHAR2
    ) AS
        v_customer_status  TBL_CUSTOMER_MASTER.STATUS%TYPE;
        v_ltv_ratio        NUMBER;
    BEGIN
        SELECT STATUS INTO v_customer_status
          FROM TBL_CUSTOMER_MASTER
         WHERE CUSTOMER_ID = p_customer_id;

        IF v_customer_status != 'ACTIVE' THEN
            p_result_code := 'CUSTOMER_INACTIVE';
            RETURN;
        END IF;

        v_ltv_ratio := p_loan_amount / p_vehicle_price;
        IF v_ltv_ratio > 0.9 THEN
            p_result_code := 'LTV_EXCEEDED';
            RETURN;
        END IF;

        IF p_loan_period > 60 THEN
            p_result_code := 'PERIOD_EXCEEDED';
            RETURN;
        END IF;

        INSERT INTO TBL_LOAN_APPLICATION (
            APPLICATION_ID, CUSTOMER_ID, VEHICLE_PRICE,
            LOAN_AMOUNT, LOAN_PERIOD, STATUS, APPLY_DATE
        ) VALUES (
            SEQ_LOAN_APPLICATION.NEXTVAL, p_customer_id, p_vehicle_price,
            p_loan_amount, p_loan_period, 'RECEIVED', SYSDATE
        ) RETURNING APPLICATION_ID INTO p_application_id;

        p_result_code := 'SUCCESS';

        PROC_CREDIT_EVALUATION(p_application_id, p_result_code);

    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            p_result_code := 'CUSTOMER_NOT_FOUND';
        WHEN OTHERS THEN
            p_result_code := 'SYSTEM_ERROR';
            ROLLBACK;
    END PROC_LOAN_APPLICATION_RECEIVE;


    PROCEDURE PROC_CREDIT_EVALUATION (
        p_application_id   IN  TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_result_code      OUT VARCHAR2
    ) AS
        v_customer_id      TBL_LOAN_APPLICATION.CUSTOMER_ID%TYPE;
        v_credit_score     NUMBER;
        v_overdue_count    NUMBER;
        v_loan_limit       NUMBER;
        v_loan_amount      TBL_LOAN_APPLICATION.LOAN_AMOUNT%TYPE;
    BEGIN
        SELECT CUSTOMER_ID, LOAN_AMOUNT
          INTO v_customer_id, v_loan_amount
          FROM TBL_LOAN_APPLICATION
         WHERE APPLICATION_ID = p_application_id;

        SELECT CREDIT_SCORE
          INTO v_credit_score
          FROM TBL_CREDIT_SCORE
         WHERE CUSTOMER_ID = v_customer_id
           AND EVAL_DATE = (SELECT MAX(EVAL_DATE)
                              FROM TBL_CREDIT_SCORE
                             WHERE CUSTOMER_ID = v_customer_id);

        SELECT COUNT(*)
          INTO v_overdue_count
          FROM TBL_OVERDUE_HISTORY
         WHERE CUSTOMER_ID = v_customer_id
           AND OVERDUE_DATE >= ADD_MONTHS(SYSDATE, -12);

        IF v_credit_score < 600 OR v_overdue_count >= 3 THEN
            UPDATE TBL_LOAN_APPLICATION
               SET STATUS = 'REJECTED',
                   REJECT_REASON = 'CREDIT_LOW'
             WHERE APPLICATION_ID = p_application_id;

            INSERT INTO TBL_APPROVAL_HISTORY (
                HISTORY_ID, APPLICATION_ID, EVAL_TYPE, RESULT, EVAL_DATE
            ) VALUES (
                SEQ_APPROVAL_HISTORY.NEXTVAL, p_application_id, 'CREDIT',
                'REJECTED', SYSDATE
            );

            PROC_NOTIFY_APPLICANT(p_application_id, 'REJECT_CREDIT');
            p_result_code := 'CREDIT_REJECTED';
            RETURN;
        END IF;

        v_loan_limit := FUNC_LIMIT_CALCULATION(v_customer_id, v_credit_score);

        IF v_loan_amount > v_loan_limit THEN
            UPDATE TBL_LOAN_APPLICATION
               SET STATUS = 'REJECTED',
                   REJECT_REASON = 'LIMIT_EXCEEDED'
             WHERE APPLICATION_ID = p_application_id;

            INSERT INTO TBL_APPROVAL_HISTORY (
                HISTORY_ID, APPLICATION_ID, EVAL_TYPE, RESULT, EVAL_DATE
            ) VALUES (
                SEQ_APPROVAL_HISTORY.NEXTVAL, p_application_id, 'LIMIT',
                'REJECTED', SYSDATE
            );

            PROC_NOTIFY_APPLICANT(p_application_id, 'REJECT_LIMIT');
            p_result_code := 'LIMIT_REJECTED';
            RETURN;
        END IF;

        PROC_FINAL_APPROVAL(p_application_id, p_result_code);

    EXCEPTION
        WHEN OTHERS THEN
            p_result_code := 'EVAL_ERROR';
            ROLLBACK;
    END PROC_CREDIT_EVALUATION;


    FUNCTION FUNC_LIMIT_CALCULATION (
        p_customer_id      IN  TBL_CUSTOMER_MASTER.CUSTOMER_ID%TYPE,
        p_credit_score     IN  NUMBER
    ) RETURN NUMBER AS
        v_annual_income    NUMBER;
        v_base_limit       NUMBER;
        v_score_factor     NUMBER;
    BEGIN
        SELECT ANNUAL_INCOME
          INTO v_annual_income
          FROM TBL_CUSTOMER_MASTER
         WHERE CUSTOMER_ID = p_customer_id;

        v_base_limit := v_annual_income * 5;

        IF p_credit_score >= 800 THEN
            v_score_factor := 1.5;
        ELSIF p_credit_score >= 700 THEN
            v_score_factor := 1.2;
        ELSIF p_credit_score >= 600 THEN
            v_score_factor := 1.0;
        ELSE
            v_score_factor := 0.7;
        END IF;

        RETURN v_base_limit * v_score_factor;
    END FUNC_LIMIT_CALCULATION;


    PROCEDURE PROC_FINAL_APPROVAL (
        p_application_id   IN  TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_result_code      OUT VARCHAR2
    ) AS
    BEGIN
        UPDATE TBL_LOAN_APPLICATION
           SET STATUS = 'APPROVED',
               APPROVE_DATE = SYSDATE
         WHERE APPLICATION_ID = p_application_id;

        INSERT INTO TBL_APPROVAL_HISTORY (
            HISTORY_ID, APPLICATION_ID, EVAL_TYPE, RESULT, EVAL_DATE
        ) VALUES (
            SEQ_APPROVAL_HISTORY.NEXTVAL, p_application_id, 'FINAL',
            'APPROVED', SYSDATE
        );

        PROC_NOTIFY_APPLICANT(p_application_id, 'APPROVED');
        p_result_code := 'APPROVED';

    EXCEPTION
        WHEN OTHERS THEN
            p_result_code := 'APPROVAL_ERROR';
            ROLLBACK;
    END PROC_FINAL_APPROVAL;


    PROCEDURE PROC_NOTIFY_APPLICANT (
        p_application_id   IN  TBL_LOAN_APPLICATION.APPLICATION_ID%TYPE,
        p_notify_type      IN  VARCHAR2
    ) AS
        v_phone            TBL_CUSTOMER_MASTER.PHONE%TYPE;
        v_message          VARCHAR2(500);
    BEGIN
        SELECT c.PHONE
          INTO v_phone
          FROM TBL_LOAN_APPLICATION a
          JOIN TBL_CUSTOMER_MASTER c ON a.CUSTOMER_ID = c.CUSTOMER_ID
         WHERE a.APPLICATION_ID = p_application_id;

        v_message := CASE p_notify_type
            WHEN 'APPROVED'      THEN '오토론 승인이 완료되었습니다.'
            WHEN 'REJECT_CREDIT' THEN '신용평가 결과 승인이 어렵습니다.'
            WHEN 'REJECT_LIMIT'  THEN '신청 금액이 한도를 초과합니다.'
            ELSE '알 수 없는 사유'
        END;

        INSERT INTO TBL_NOTIFICATION_LOG (
            LOG_ID, APPLICATION_ID, NOTIFY_TYPE,
            PHONE, MESSAGE, SEND_DATE
        ) VALUES (
            SEQ_NOTIFICATION_LOG.NEXTVAL, p_application_id, p_notify_type,
            v_phone, v_message, SYSDATE
        );

    EXCEPTION
        WHEN OTHERS THEN
            NULL;
    END PROC_NOTIFY_APPLICANT;

END PKG_AUTO_LOAN_APPROVAL;
/
