import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.prowidesoftware.swift.model.SwiftTagListBlock;
import com.prowidesoftware.swift.model.Tag;
import com.prowidesoftware.swift.model.field.Field;
import com.prowidesoftware.swift.model.mt.AbstractMT;
import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class MtProwideProbe {
    private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().setPrettyPrinting().create();

    private MtProwideProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            throw new IllegalArgumentException("command required");
        }
        if ("field-defs".equals(args[0])) {
            if (args.length < 3) {
                throw new IllegalArgumentException("usage: field-defs OUT TAG...");
            }
            writeJson(fieldDefinitions(args), Path.of(args[1]));
            return;
        }
        if ("parse".equals(args[0])) {
            if (args.length != 4) {
                throw new IllegalArgumentException("usage: parse MTnnn INPUT OUT");
            }
            writeJson(parseMessage(args[1], Path.of(args[2])), Path.of(args[3]));
            return;
        }
        throw new IllegalArgumentException("unknown command: " + args[0]);
    }

    private static List<Map<String, Object>> fieldDefinitions(String[] args) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int i = 2; i < args.length; i++) {
            rows.add(fieldDefinition(args[i]));
        }
        return rows;
    }

    private static Map<String, Object> fieldDefinition(String tag) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("tag", tag);
        String className = "com.prowidesoftware.swift.model.field.Field" + tag;
        row.put("className", className);
        try {
            Class<?> clazz = Class.forName(className);
            Field field = (Field) clazz.getConstructor().newInstance();
            row.put("sru", staticInteger(clazz, "SRU"));
            row.put("typesPattern", field.typesPattern());
            row.put("parserPattern", optionalStringMethod(field, clazz, "parserPattern"));
            row.put("validatorPattern", field.validatorPattern());
            row.put("componentLabels", field.getComponentLabels());
            row.put("componentsSize", field.componentsSize());
            row.put("optionalComponents", optionalComponents(field));
            row.put("generic", field.isGeneric());
        } catch (Exception error) {
            row.put("error", error.getClass().getSimpleName() + ": " + error.getMessage());
        }
        return row;
    }

    private static Map<String, Object> parseMessage(String messageType, Path input) throws Exception {
        Class<?> clazz = messageClass(messageType);
        Method parse = clazz.getMethod("parse", String.class);
        String fin = Files.readString(input, StandardCharsets.UTF_8);
        AbstractMT mt = (AbstractMT) parse.invoke(null, fin);
        SwiftTagListBlock block4 = mt.getSwiftMessage().getBlock4();
        List<Map<String, Object>> tags = new ArrayList<>();
        int index = 1;
        for (Tag tag : block4.getTags()) {
            tags.add(parsedTag(index, tag));
            index++;
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("requestedMessageType", messageType);
        result.put("parsedMessageType", "MT" + mt.getMessageType());
        result.put("sru", staticInteger(clazz, "SRU"));
        result.put("tagCount", tags.size());
        result.put("tags", tags);
        return result;
    }

    private static Map<String, Object> parsedTag(int index, Tag tag) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("index", index);
        row.put("tag", tag.getName());
        row.put("value", tag.getValue());
        try {
            Field field = Field.getField(tag);
            row.put("fieldClass", field.getClass().getName());
            row.put("qualifier", optionalStringMethod(field, field.getClass(), "getQualifier"));
        } catch (Exception error) {
            row.put("fieldClass", null);
            row.put("qualifier", qualifierFromValue(tag.getValue()));
        }
        return row;
    }

    private static Class<?> messageClass(String messageType) throws ClassNotFoundException {
        if (!messageType.matches("MT\\d{3}")) {
            throw new IllegalArgumentException("message type must look like MTnnn: " + messageType);
        }
        String category = messageType.substring(2, 3);
        return Class.forName(
                "com.prowidesoftware.swift.model.mt.mt" + category + "xx." + messageType);
    }

    private static Integer staticInteger(Class<?> clazz, String fieldName) {
        try {
            return Integer.valueOf(clazz.getField(fieldName).getInt(null));
        } catch (Exception error) {
            return null;
        }
    }

    private static String optionalStringMethod(Field field, Class<?> clazz, String methodName) {
        try {
            Method method = clazz.getMethod(methodName);
            Object value = method.invoke(field);
            return value == null ? null : value.toString();
        } catch (Exception error) {
            return null;
        }
    }

    private static List<Integer> optionalComponents(Field field) {
        List<Integer> components = new ArrayList<>();
        for (int i = 1; i <= field.componentsSize(); i++) {
            if (field.isOptional(i)) {
                components.add(Integer.valueOf(i));
            }
        }
        return components;
    }

    private static String qualifierFromValue(String value) {
        if (value != null && value.matches("^:[A-Z0-9]{4}//.*")) {
            return value.substring(1, 5);
        }
        return null;
    }

    private static void writeJson(Object value, Path path) throws IOException {
        if (path.getParent() != null) {
            Files.createDirectories(path.getParent());
        }
        Files.writeString(path, GSON.toJson(value) + "\n", StandardCharsets.UTF_8);
    }
}
