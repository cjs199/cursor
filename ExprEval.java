import java.util.Scanner;

/**
 * Evaluates integer arithmetic expressions with +, -, *, /, parentheses, and unary minus.
 * Whitespace is ignored. Division truncates toward zero; division by zero is an error.
 */
public class ExprEval {

    private static final class Parser {
        private final String s;
        private int pos;
        private boolean err;

        Parser(String s) {
            this.s = s;
            this.pos = 0;
            this.err = false;
        }

        long eval() {
            if (s == null) {
                err = true;
                return 0;
            }
            skipWs();
            if (pos >= s.length()) {
                err = true;
                return 0;
            }
            long value = parseExpr();
            skipWs();
            if (!err && pos < s.length()) {
                err = true;
            }
            return value;
        }

        boolean hasError() {
            return err;
        }

        private void skipWs() {
            while (pos < s.length() && Character.isWhitespace(s.charAt(pos))) {
                pos++;
            }
        }

        private char peek() {
            skipWs();
            if (pos < s.length()) {
                return s.charAt(pos);
            }
            return '\0';
        }

        private char next() {
            skipWs();
            if (pos < s.length()) {
                return s.charAt(pos++);
            }
            return '\0';
        }

        private long parseExpr() {
            long left = parseTerm();
            while (!err) {
                char op = peek();
                if (op != '+' && op != '-') {
                    break;
                }
                next();
                long right = parseTerm();
                if (err) {
                    break;
                }
                if (op == '+') {
                    left += right;
                } else {
                    left -= right;
                }
            }
            return left;
        }

        private long parseTerm() {
            long left = parseFactor();
            while (!err) {
                char op = peek();
                if (op != '*' && op != '/') {
                    break;
                }
                next();
                long right = parseFactor();
                if (err) {
                    break;
                }
                if (op == '*') {
                    left *= right;
                } else {
                    if (right == 0) {
                        err = true;
                        return 0;
                    }
                    left /= right;
                }
            }
            return left;
        }

        private long parseFactor() {
            char c = peek();
            if (c == '-') {
                next();
                return -parseFactor();
            }
            if (c == '(') {
                next();
                long inner = parseExpr();
                char closing = next();
                if (closing != ')') {
                    err = true;
                }
                return inner;
            }
            return parseNumber();
        }

        private long parseNumber() {
            if (!Character.isDigit(peek())) {
                err = true;
                return 0;
            }
            long res = 0;
            boolean firstDigit = true;
            while (pos < s.length() && Character.isDigit(s.charAt(pos))) {
                char ch = s.charAt(pos);
                if (firstDigit) {
                    if (ch == '0' && pos + 1 < s.length() && Character.isDigit(s.charAt(pos + 1))) {
                        err = true;
                        return 0;
                    }
                    firstDigit = false;
                }
                res = res * 10 + (ch - '0');
                pos++;
            }
            return res;
        }
    }

    private static String evaluateToString(String input) {
        Parser p = new Parser(input);
        long value = p.eval();
        if (p.hasError()) {
            return "ERROR";
        }
        return Long.toString(value);
    }

    public static void main(String[] args) {
        String[] tests = {
            "3+4*2",
            "(1+2)*(3+4)",
            "10 / 3",
            "-5+3",
            "-(3*(-2))",
            "42",
            "0-1-2",
            "8/3/2",
            "5/-2",
            "1+2*3-4/5+6",
            "((2+3)*4)",
            "(1+(2*3)+((4)))+5",
            "2147483640+7",
            "01+2",
            "3+*4",
            "()",
            "(1+2",
            "1/0",
            "0/1",
            "-0"
        };

        for (int i = 0; i < tests.length; i++) {
            System.out.println("CASE " + (i + 1) + ": " + evaluateToString(tests[i]));
        }

        Scanner sc = new Scanner(System.in);
        if (sc.hasNextLine()) {
            String line = sc.nextLine();
            System.out.println(evaluateToString(line));
        }
    }
}
